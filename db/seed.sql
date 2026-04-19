-- Seed data: 12 demo deals covering all validation scenarios
-- Covers: multiple currencies, risk levels, FCC flags, KYC expiry,
--         active/closed status, fixed/floating rates, fees/no-fees

-- ============================================================
-- Firm Balances  (insert before loan_info because of FK reference)
-- ============================================================
INSERT INTO firm_balance (firm_account, currency, balance) VALUES
  (1001, 'USD', 48500000.00),   -- large USD pool
  (1001, 'GBP', 19800000.00),   -- GBP pool for same firm
  (1002, 'EUR', 29700000.00),   -- EUR pool
  (1002, 'USD', 14850000.00),   -- second USD pool
  (1003, 'USD',  9900000.00),   -- smaller firm
  (1004, 'GBP',  4950000.00)    -- smallest firm
ON CONFLICT DO NOTHING;

-- ============================================================
-- Borrower Accounts
-- ============================================================
INSERT INTO borrower_account
  (borrower_account, borrower_name, country, email, borrower_type, risk_meter, kyc_status, kyc_valid_till, fcc_flag)
VALUES
  -- 1: Clean borrower, Low risk, USD deal
  (2001, 'Apex Manufacturing Corp',      'United States', 'treasury@apexmfg.com',       'Corporate',              'Low',    TRUE,  '2027-06-30', FALSE),
  -- 2: Low risk, GBP deal, fees applicable
  (2002, 'Sterling Retail Holdings Ltd', 'United Kingdom','finance@sterlingretail.co.uk','Corporate',              'Low',    TRUE,  '2026-12-31', FALSE),
  -- 3: Medium risk, EUR deal
  (2003, 'Eurocorp Industries SA',       'France',        'loans@eurocorp.fr',           'Corporate',              'Medium', TRUE,  '2026-09-30', FALSE),
  -- 4: Medium risk, floating rate, USD
  (2004, 'Atlantic Shipping Partners',   'United States', 'cfo@atlanticship.com',        'Corporate',              'Medium', TRUE,  '2025-12-31', FALSE),
  -- 5: Low risk, FCC flagged (demo HIL trigger)
  (2005, 'Global Trade Finance LLC',     'United States', 'ops@globaltradefinance.com',  'Financial Institution',  'Low',    TRUE,  '2027-03-31', TRUE),
  -- 6: Low risk, KYC expiring soon — use payment_date > kyc_valid_till to trigger HIL
  (2006, 'Pacific Ventures Pte Ltd',     'Singapore',     'finance@pacificventures.sg',  'Corporate',              'Low',    TRUE,  '2025-05-01', FALSE),
  -- 7: High risk borrower (demo risk HIL trigger)
  (2007, 'Redstone Energy Corp',         'United States', 'ir@redstoneenergy.com',       'Corporate',              'High',   TRUE,  '2026-06-30', FALSE),
  -- 8: Financial institution, EUR, fees
  (2008, 'Nordic Capital Bank',          'Sweden',        'syndications@nordiccap.se',   'Financial Institution',  'Low',    TRUE,  '2027-12-31', FALSE),
  -- 9: Government borrower, USD
  (2009, 'Republic of Meridia Finance',  'Meridia',       'debtoffice@meridia.gov',      'Government',             'Medium', TRUE,  '2026-03-31', FALSE),
  -- 10: Already-closed deal borrower
  (2010, 'Silvergate Properties Inc',    'Canada',        'treasury@silvergate.ca',      'Corporate',              'Low',    TRUE,  '2027-06-30', FALSE),
  -- 11: KYC expired borrower
  (2011, 'Harbour Logistics Ltd',        'United Kingdom','finance@harbourlogistics.co.uk','Corporate',             'Low',    FALSE, '2024-01-01', FALSE),
  -- 12: Large conglomerate
  (2012, 'Titan Group Holdings',         'Germany',       'dcm@titangroup.de',           'Corporate',              'Medium', TRUE,  '2027-09-30', FALSE)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Loan Info (12 deals)
-- ============================================================
INSERT INTO loan_info
  (deal_name, committed_amount, funded, margin, interest_rate, interest_rate_type,
   origination_date, maturity_date, status, fees_applicable, currency, ca_pdf_url,
   borrower_account, firm_account)
VALUES
  -- Deal 1: Clean active USD deal — standard drawdown demo
  ('Apex Term Loan Facility 2024',
   50000000.00, 10000000.00, NULL, 5.25, 'Fixed',
   '2024-01-15', '2029-01-15', 'Active', FALSE, 'USD',
   'https://r2.example.com/CA_20240115_001.pdf', 2001, 1001),

  -- Deal 2: GBP deal with fees — fee payment demo
  ('Sterling Revolving Credit Facility',
   20000000.00, 5000000.00, NULL, 4.75, 'Fixed',
   '2023-06-01', '2028-06-01', 'Active', TRUE, 'GBP',
   'https://r2.example.com/CA_20230601_002.pdf', 2002, 1001),

  -- Deal 3: EUR floating rate — interest payment demo
  ('Eurocorp Syndicated Term Loan',
   30000000.00, 15000000.00, 1.50, 3.50, 'Floating',
   '2023-09-15', '2028-09-15', 'Active', FALSE, 'EUR',
   'https://r2.example.com/CA_20230915_003.pdf', 2003, 1002),

  -- Deal 4: USD floating — repayment demo
  ('Atlantic Shipping Facility 2023',
   15000000.00, 8000000.00, 2.00, 5.00, 'Floating',
   '2023-03-01', '2027-03-01', 'Active', TRUE, 'USD',
   'https://r2.example.com/CA_20230301_004.pdf', 2004, 1002),

  -- Deal 5: FCC flagged borrower — any notice triggers HIL
  ('Global Trade Finance Line of Credit',
   10000000.00, 2000000.00, NULL, 6.00, 'Fixed',
   '2024-03-01', '2027-03-01', 'Active', FALSE, 'USD',
   'https://r2.example.com/CA_20240301_005.pdf', 2005, 1003),

  -- Deal 6: KYC expiry triggers HIL for notices dated after 2025-05-01
  ('Pacific Ventures Bridge Loan',
   5000000.00, 1000000.00, NULL, 5.50, 'Fixed',
   '2024-06-01', '2027-06-01', 'Active', FALSE, 'USD',
   'https://r2.example.com/CA_20240601_006.pdf', 2006, 1003),

  -- Deal 7: High risk borrower — risk assessment may escalate
  ('Redstone Energy Project Finance',
   25000000.00, 12000000.00, 2.50, 4.00, 'Floating',
   '2023-07-01', '2028-07-01', 'Active', TRUE, 'USD',
   'https://r2.example.com/CA_20230701_007.pdf', 2007, 1001),

  -- Deal 8: EUR financial institution with fees
  ('Nordic Capital Senior Facility',
   35000000.00, 20000000.00, NULL, 3.75, 'Fixed',
   '2022-11-01', '2027-11-01', 'Active', TRUE, 'EUR',
   'https://r2.example.com/CA_20221101_008.pdf', 2008, 1002),

  -- Deal 9: Government borrower, medium risk, USD
  ('Republic of Meridia Sovereign Loan',
   100000000.00, 40000000.00, NULL, 4.50, 'Fixed',
   '2023-01-01', '2030-01-01', 'Active', FALSE, 'USD',
   'https://r2.example.com/CA_20230101_009.pdf', 2009, 1001),

  -- Deal 10: Already CLOSED deal — any notice should hard-stop
  ('Silvergate Properties Term Loan',
   8000000.00, 0.00, NULL, 4.00, 'Fixed',
   '2020-01-01', '2024-01-01', 'Closed', FALSE, 'USD',
   'https://r2.example.com/CA_20200101_010.pdf', 2010, 1004),

  -- Deal 11: KYC expired borrower — any notice triggers KYC HIL
  ('Harbour Logistics Working Capital',
   6000000.00, 3000000.00, NULL, 5.75, 'Fixed',
   '2023-08-01', '2027-08-01', 'Active', FALSE, 'GBP',
   'https://r2.example.com/CA_20230801_011.pdf', 2011, 1004),

  -- Deal 12: EUR large deal — full repayment demo (funded = 0 when fully repaid)
  ('Titan Group Acquisition Facility',
   40000000.00, 30000000.00, 1.75, 3.25, 'Floating',
   '2022-05-01', '2029-05-01', 'Active', TRUE, 'EUR',
   'https://r2.example.com/CA_20220501_012.pdf', 2012, 1002)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Transaction Log — sample historical transactions for duplicate
-- detection demos and audit trail completeness
-- ============================================================
INSERT INTO transaction_log
  (deal_id, notice_type, notice_pdf_url, amount, currency,
   notice_date, processed_at, agent_decision, human_in_loop_triggered,
   hil_triggers, hil_decisions, final_outcome, failure_reason)
VALUES
  -- Deal 1: prior drawdown
  (1, 'Drawdown', 'https://r2.example.com/Notice_20240201_001.pdf',
   10000000.00, 'USD', '2024-02-01', '2024-02-01 09:15:00+00',
   'Approved', TRUE,
   '[{"reason": "Drawdown Approval", "details": {"amount": 10000000}}]',
   '[{"reason": "Drawdown Approval", "decision": "Approved"}]',
   'Success', NULL),

  -- Deal 3: prior interest payment
  (3, 'Interest Payment', 'https://r2.example.com/Notice_20240115_003.pdf',
   262500.00, 'EUR', '2024-01-15', '2024-01-15 11:00:00+00',
   'Approved', FALSE,
   '[]', '[]', 'Success', NULL),

  -- Deal 4: prior repayment
  (4, 'Repayment', 'https://r2.example.com/Notice_20240301_004.pdf',
   2000000.00, 'USD', '2024-03-01', '2024-03-01 14:30:00+00',
   'Approved', TRUE,
   '[{"reason": "Drawdown Approval", "details": {}}]',
   '[{"reason": "Drawdown Approval", "decision": "Approved"}]',
   'Success', NULL),

  -- Deal 7: prior fee payment
  (7, 'Fee Payment', 'https://r2.example.com/Notice_20240401_007.pdf',
   125000.00, 'USD', '2024-04-01', '2024-04-01 10:00:00+00',
   'Approved', FALSE,
   '[]', '[]', 'Success', NULL)
ON CONFLICT DO NOTHING;
