# What's next: metrics we do not show yet, and what each one needs

Source of the list: feedback from a judge and industry mentor (Isma). Today the Dashboard shows a **Retention outlook** built from the data we already connect (usage, support, billing, calls). The metrics below need data we do not have yet. Each one is a connector, not a rebuild.

## Next (about one day of work each)
| Metric | Why CSMs want it | What we need | How it fits |
|---|---|---|---|
| CSAT | Shows how customers rate each support interaction | Ticket satisfaction ratings (Zendesk, Intercom, Freshdesk) | One more column in `tickets.csv`, then a per-customer and average CSAT tile |
| NPS | Standard loyalty score that leadership already tracks | Survey export (Delighted, Typeform, HubSpot) | New `surveys.csv`: account, date, score, comment. Comments get the same quote-and-verify treatment as calls |
| QBR / EBR completion | Shows whether strategic reviews actually happen | A call or meeting type in the calendar or CRM | Add a `kind` column to `conversations.csv` (today every conversation counts as a call) |

## Later (needs billing history or CRM/finance data)
| Metric | What we need |
|---|---|
| Gross revenue retention (GRR) | ARR per customer at the start of a 12-month period, to compare with today. Today we show a forward-looking outlook instead |
| Net revenue retention (NRR) and expansion MRR/ARR | The same history, plus upsell and cross-sell lines on invoices |
| Logo churn rate | Which customers were lost in the past 12 months |
| Time to value (TTV) | Contract start date and the date of the first meaningful use (CRM plus product events) |
| Customer lifetime value (LTV) | Customer lifespan and margin from finance |
| LTV to CAC ratio | Sales and marketing cost per new customer from finance |

## Honest limits to say out loud
- Revenue retained in the outlook assumes every high-risk renewal is lost. It is a worst case, not a forecast.
- Contraction per seat is estimated from the price per seat after the cut.
- Call coverage counts any recorded conversation, not only QBRs.
- We never show a made-up NPS or CSAT. Without a survey source the tile does not appear.
