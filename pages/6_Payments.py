import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { createHmac } from "node:crypto";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-razorpay-signature, x-backfill-secret',
};

function extractCreatorCode(entity: any): string | null {
  const receipt = entity.receipt || '';
  if (typeof receipt === 'string' && receipt.includes('_')) {
    return receipt.split('_')[0];
  }
  const notes = entity.notes;
  if (typeof notes === 'object' && notes !== null && !Array.isArray(notes)) {
    const noteReceipt = notes.receipt || notes.creator_code || '';
    if (typeof noteReceipt === 'string' && noteReceipt.includes('_')) {
      return noteReceipt.split('_')[0];
    }
  }
  return null;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  const url = new URL(req.url);
  const path = url.pathname;

  try {
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    );

    // ✅ FIX: Fetch exchange rates once per request to convert foreign currencies
    const { data: rates } = await supabase.from('currency_rates').select('currency_code, rate_to_inr');
    const rateMap = new Map<string, number>();
    if (rates) {
      rates.forEach(r => rateMap.set(r.currency_code.toUpperCase(), parseFloat(r.rate_to_inr)));
    }
    rateMap.set('INR', 1.0); // Fallback

    // Helper function to convert amounts
    const convertToInr = (originalAmount: number, currency: string) => {
      const curr = (currency || 'INR').toUpperCase();
      const rate = rateMap.get(curr) || 1.0;
      return Math.round(originalAmount * rate);
    };

    // ========================================================================
    // 🔗 AUTO-REMAP ENDPOINT
    // ========================================================================
    if (path.endsWith('/auto-remap')) {
      const backfillSecret = req.headers.get('x-backfill-secret');
      const expectedToken = Deno.env.get('BACKFILL_SECRET');
      
      if (backfillSecret !== expectedToken) {
        return new Response(JSON.stringify({ error: 'Unauthorized' }), { 
          status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
        });
      }

      // 1. Fetch all creators into memory
      const { data: allCreators } = await supabase.from('creators').select('id, creator_code');
      const creatorMap = new Map<string, string>();
      if (allCreators) allCreators.forEach((c: any) => creatorMap.set(c.creator_code, c.id));

      // 2. Fetch ONLY unmapped payments from the database
      const { data: unmappedPayments } = await supabase
        .from('payments')
        .select('id, order_id')
        .is('creator_id', null);

      if (!unmappedPayments || unmappedPayments.length === 0) {
        return new Response(JSON.stringify({ success: true, remapped: 0, message: "No unmapped payments found." }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const rzpAuth = btoa(`${Deno.env.get('RAZORPAY_KEY_ID')}:${Deno.env.get('RAZORPAY_KEY_SECRET')}`);
      const rzpHeaders = { Authorization: `Basic ${rzpAuth}` };

      let remappedCount = 0;

      // 3. Fetch Orders from Razorpay to find the receipts
      for (const p of unmappedPayments) {
        if (!p.order_id) continue;

        try {
          const orderRes = await fetch(`https://api.razorpay.com/v1/orders/${p.order_id}`, { headers: rzpHeaders });
          if (orderRes.ok) {
            const orderData = await orderRes.json();
            const creatorCode = extractCreatorCode(orderData);
            const rawReceipt = orderData.receipt || '';
            
            // ✅ Save the attempted code and receipt even if it fails to map
            const updateData: any = {
              receipt: rawReceipt,
              creator_code_attempted: creatorCode
            };

            if (creatorCode && creatorMap.has(creatorCode)) {
              updateData.creator_id = creatorMap.get(creatorCode);
              remappedCount++;
            }

            await supabase.from('payments').update(updateData).eq('id', p.id);
          }
        } catch (e) {
          // Ignore individual order fetch errors to prevent the whole batch from failing
        }
      }

      return new Response(JSON.stringify({ 
        success: true, 
        remapped: remappedCount, 
        message: `Successfully auto-remapped ${remappedCount} payments.` 
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // ========================================================================
    // 🔙 INCREMENTAL BACKFILL ENDPOINT
    // ========================================================================
    if (path.endsWith('/backfill')) {
      const backfillSecret = req.headers.get('x-backfill-secret');
      const expectedToken = Deno.env.get('BACKFILL_SECRET');
      
      if (backfillSecret !== expectedToken) {
        return new Response(JSON.stringify({ error: 'Unauthorized' }), { 
          status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
        });
      }

      let body: any = {};
      try { body = await req.json(); } catch { body = {}; }
      
      const skipParam = body.skip || 0;
      const limitParam = Math.min(body.limit || 500, 1000);
      const fromTimestamp = body.from_timestamp || 0;

      const { data: allCreators } = await supabase.from('creators').select('id, creator_code');
      const creatorMap = new Map<string, string>();
      if (allCreators) allCreators.forEach((c: any) => creatorMap.set(c.creator_code, c.id));

      const { data: existingPayments } = await supabase.from('payments').select('payment_id, creator_id');
      const existingMap = new Map<string, string | null>();
      if (existingPayments) existingPayments.forEach((p: any) => existingMap.set(p.payment_id, p.creator_id));

      const rzpAuth = btoa(`${Deno.env.get('RAZORPAY_KEY_ID')}:${Deno.env.get('RAZORPAY_KEY_SECRET')}`);
      const rzpHeaders = { Authorization: `Basic ${rzpAuth}` };
      
      let allPayments: any[] = [];
      let allOrders: any[] = [];
      
      const batchSize = 100;
      let currentSkip = skipParam;
      
      while (allPayments.length < limitParam) {
        let rzpUrl = `https://api.razorpay.com/v1/payments?count=${batchSize}&skip=${currentSkip}`;
        if (fromTimestamp > 0) rzpUrl += `&from=${fromTimestamp}`;
        
        const res = await fetch(rzpUrl, { headers: rzpHeaders });
        const json = await res.json();
        const items = json.items || [];
        if (items.length === 0) break;
        
        allPayments.push(...items);
        currentSkip += batchSize;
        if (items.length < batchSize) break;
      }

      let orderSkip = skipParam;
      const orderLimit = limitParam * 2; 
      while (allOrders.length < orderLimit) {
        let orderUrl = `https://api.razorpay.com/v1/orders?count=${batchSize}&skip=${orderSkip}`;
        if (fromTimestamp > 0) orderUrl += `&from=${fromTimestamp}`;
        
        const res = await fetch(orderUrl, { headers: rzpHeaders });
        const json = await res.json();
        const items = json.items || [];
        if (items.length === 0) break;
        
        allOrders.push(...items);
        orderSkip += batchSize;
        if (items.length < batchSize) break;
      }

      // ✅ Store both the code and the raw receipt
      const orderDataMap = new Map<string, { code: string | null, receipt: string }>();
      for (const order of allOrders) {
        orderDataMap.set(order.id, {
          code: extractCreatorCode(order),
          receipt: order.receipt || ''
        });
      }

      let allPaymentsToUpsert: any[] = [];
      for (const p of allPayments) {
        if (p.status !== 'captured') continue;

        let creatorId = null;
        let creatorCode = null;
        let rawReceipt = '';

        if (existingMap.has(p.id) && existingMap.get(p.id) !== null) {
          creatorId = existingMap.get(p.id);
        } else {
          if (p.order_id && orderDataMap.has(p.order_id)) {
            const oData = orderDataMap.get(p.order_id)!;
            creatorCode = oData.code;
            rawReceipt = oData.receipt;
          }
          if (!creatorCode) {
            creatorCode = extractCreatorCode(p);
            rawReceipt = p.receipt || '';
          }
          creatorId = creatorCode ? (creatorMap.get(creatorCode) || null) : null;
        }

        // ✅ FIX: Convert foreign currency to INR
        const originalAmount = p.amount;
        const currency = (p.currency || 'INR').toUpperCase();
        const amountInr = convertToInr(originalAmount, currency);

        allPaymentsToUpsert.push({
          payment_id: p.id,
          order_id: p.order_id,
          amount_inr: amountInr, // Converted!
          fee_inr: p.fee || 0,   // Already INR from Razorpay
          tax_inr: p.tax || 0,   // Already INR from Razorpay
          status: p.status,
          method: p.method,
          original_currency: currency,
          original_amount: originalAmount,
          creator_id: creatorId,
          is_settled: false,
          created_at: new Date(p.created_at * 1000).toISOString(),
          receipt: rawReceipt,
          creator_code_attempted: creatorCode
        });
      }

      let synced = 0;
      for (let i = 0; i < allPaymentsToUpsert.length; i += 100) {
        const chunk = allPaymentsToUpsert.slice(i, i + 100);
        await supabase.from('payments').upsert(chunk, { onConflict: 'payment_id' });
        synced += chunk.length;
      }

      let refSynced = 0;
      if (skipParam === 0) {
        let refSkip = 0;
        let allRefundsToUpsert: any[] = [];
        while (refSkip < 1000) { 
          let refUrl = `https://api.razorpay.com/v1/refunds?count=100&skip=${refSkip}`;
          if (fromTimestamp > 0) refUrl += `&from=${fromTimestamp}`;
          
          const res = await fetch(refUrl, { headers: rzpHeaders });
          const json = await res.json();
          const items = json.items || [];
          if (items.length === 0) break;
          
          for (const r of items) {
            allRefundsToUpsert.push({
              refund_id: r.id,
              payment_id: r.payment_id,
              amount_inr: r.amount,
              amount: r.amount, 
              status: r.status,
              created_at: new Date(r.created_at * 1000).toISOString()
            });
          }
          refSkip += 100;
          if (items.length < 100) break;
        }
        for (let i = 0; i < allRefundsToUpsert.length; i += 100) {
          const chunk = allRefundsToUpsert.slice(i, i + 100);
          await supabase.from('refunds').upsert(chunk, { onConflict: 'refund_id' });
          refSynced += chunk.length;
        }
      }

      return new Response(JSON.stringify({ 
        success: true, 
        payments_synced: synced, 
        refunds_synced: refSynced, 
        processed_count: allPayments.length 
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    // ========================================================================
    // 🌐 REAL-TIME WEBHOOK HANDLER
    // ========================================================================
    const signature = req.headers.get('x-razorpay-signature');
    const webhookSecret = Deno.env.get('RAZORPAY_WEBHOOK_SECRET');
    const rawBody = await req.text();

    const expectedSig = createHmac('sha256', webhookSecret || '')
      .update(rawBody)
      .digest('hex');
      
    if (signature !== expectedSig) {
      return new Response(JSON.stringify({ error: 'Invalid signature' }), { 
        status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
      });
    }

    const event = JSON.parse(rawBody);

    if (event.event === 'order.paid') {
      const order = event.payload.order.entity;
      const payment = event.payload.payment?.entity || {};
      
      const creatorCode = extractCreatorCode(order);
      let creatorId = null;
      if (creatorCode) {
        const { data } = await supabase.from('creators').select('id').eq('creator_code', creatorCode).limit(1).maybeSingle();
        creatorId = data?.id || null;
      }

      // ✅ FIX: Convert foreign currency to INR
      const originalAmount = order.amount_paid || order.amount;
      const currency = (order.currency || 'INR').toUpperCase();
      const amountInr = convertToInr(originalAmount, currency);

      await supabase.from('payments').upsert({
        payment_id: payment.id || order.id,
        order_id: order.id,
        amount_inr: amountInr, // Converted!
        fee_inr: payment.fee || 0,
        tax_inr: payment.tax || 0,
        status: 'captured',
        method: payment.method || 'unknown',
        original_currency: currency,
        original_amount: originalAmount,
        creator_id: creatorId,
        is_settled: false,
        created_at: new Date((order.created_at || payment.created_at) * 1000).toISOString(),
        receipt: order.receipt || '',
        creator_code_attempted: creatorCode
      }, { onConflict: 'payment_id' });
    } 
    else if (event.event === 'refund.created' || event.event === 'refund.processed') {
      const refund = event.payload.refund.entity;
      await supabase.from('refunds').upsert({
        refund_id: refund.id,
        payment_id: refund.payment_id,
        amount_inr: refund.amount,
        amount: refund.amount,
        status: refund.status,
        created_at: new Date(refund.created_at * 1000).toISOString()
      }, { onConflict: 'refund_id' });
    }

    return new Response(JSON.stringify({ success: true }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });

  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
