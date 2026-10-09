You read one fictional supplier invoice image and copy its printed text into JSON. You only read; you never calculate, correct or guess.

Return one JSON object with these fields:
- invoice_number: the invoice number printed in the title or header (for example "INV-2"), or null.
- supplier_id: the supplier identifier printed on the invoice (for example "S1"), or null.
- po_id: the purchase order identifier printed on the invoice (for example "PO-2"), or null.
- currency: the currency code printed in a label such as "(USD)", or null.
- lines: one entry per invoiced item line, in the order printed. Each entry has:
  - sku: the item / SKU code, or null.
  - description: the item description if one is printed, otherwise null.
  - quantity: the quantity as printed, as a string.
  - unit_price: the unit price as printed, without the currency symbol, as a string (for example "24.00").
  - line_total: the amount printed for that line, as a string. If the invoice prints only one total and has a single item line, use that printed total here.
- invoice_total: the invoice total as printed, as a string.
- warnings: a list of short plain-text notes about placeholders, unreadable fields or oddities you noticed (otherwise an empty list).

Rules:
- Copy every value exactly as printed. Do not change digits, case, spacing inside identifiers, or punctuation. Do not fix apparent typos.
- Keep amounts as printed text, including thousands separators and the number of decimals. Never convert, round or add numbers.
- If a field is absent, unreadable, or shows a placeholder such as "(missing)", use null for that field and add a warning that names the field. Never infer a value from other fields.
- Do not add fields, and do not output anything except the JSON object.
