"""Generate sample CA and Notice PDFs for smoke testing.

Run once before tests:
    python tests/generate_sample_pdfs.py
"""

import os

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_pdfs")
os.makedirs(SAMPLE_DIR, exist_ok=True)


def _make_pdf(path: str, text: str) -> None:
    """Write a minimal text-based PDF."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    # Insert text — wrap at ~80 chars per line
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 > 80:
                lines.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        if line:
            lines.append(line)
        lines.append("")  # blank line between paragraphs

    y = 72  # top margin
    for line in lines:
        page.insert_text((72, y), line, fontsize=10)
        y += 14
        if y > page.rect.height - 72:
            page = doc.new_page()
            y = 72

    doc.save(path)
    doc.close()
    print(f"  Created: {path}")


# ---------------------------------------------------------------------------
# Sample Credit Agreement
# ---------------------------------------------------------------------------

CA_TEXT = """CREDIT AGREEMENT

Date of Agreement: 15 January 2025
Facility Name: Demo Alpha Term Loan Facility 2025

PARTIES

Borrower: Demo Borrower Corp
Account Number: 9901
Borrower Type: Corporate
Email for Notices: treasury@demoborrower.com
Country of Incorporation: United States

KYC Status: Complete
KYC Valid Until: 2027-12-31
FCC Flag: False

FACILITY TERMS

Committed Amount: USD 20,000,000
Currency: USD
Interest Rate: 5.50%
Rate Type: Fixed
Margin: N/A
Origination Date: 2025-01-15
Maturity Date: 2030-01-15
Funded: 0

RISK AND COMPLIANCE

Risk Rating: Low
Credit Risk Classification: Investment Grade

FEES

Fee Schedule: This facility carries a commitment fee of 0.25% per annum on the
undrawn committed amount payable quarterly in arrears.

FIRM ACCOUNT

Agent Account Number: 5001

CONDITIONS PRECEDENT

5.1 The Borrower shall not make a Utilisation Request unless the following conditions
are satisfied:
(a) No Event of Default is continuing or would result from the Utilisation.
(b) The representations set out in Clause 8 (Representations) are true in all
    material respects.
(c) KYC and AML checks are confirmed satisfactory.

5.2 The Agent shall not be obliged to comply with any Utilisation Request if it would
cause a breach of this Agreement.

PERMITTED PURPOSE

6.1 The Borrower shall use all amounts borrowed under this Facility solely for general
corporate purposes and working capital, including capital expenditure directly related
to the Borrower's core manufacturing operations. The proceeds shall not be used for
acquisitions, speculative investments, or any purpose that would violate applicable law.

NOTICE MECHANICS

7.1 All notices under this Facility must be delivered in writing.
7.2 Utilisation Requests must be received by the Agent no later than 3 Business Days
prior to the proposed Drawdown Date.
7.3 Repayment notices must be given no later than 5 Business Days before the
proposed repayment date.
7.4 Interest payment notices must be delivered by the Interest Payment Date.

INTEREST

8.1 The rate of interest on each Loan is 5.50% per annum (Fixed Rate).
8.2 Interest is calculated on the basis of a 365-day year.

REPAYMENT

9.1 The Borrower shall repay each Loan in full on the Maturity Date.
9.2 Voluntary prepayment is permitted on any Business Day with 5 Business Days prior
notice to the Agent.
9.3 Minimum prepayment amount: USD 500,000 or such higher amount that is an integral
multiple of USD 100,000.

REPRESENTATIONS AND WARRANTIES

The Borrower represents and warrants that it is duly incorporated, has the power to
enter into this Agreement, and that this Agreement constitutes legally binding
obligations enforceable against it.

COVENANTS

The Borrower undertakes that so long as any amounts are outstanding it will maintain
adequate insurance, provide audited financial statements within 120 days of each
financial year end, and promptly notify the Agent of any Event of Default.

GOVERNING LAW

This Agreement is governed by the laws of the State of New York.
"""

# ---------------------------------------------------------------------------
# Sample Drawdown Notice
# ---------------------------------------------------------------------------

DRAWDOWN_NOTICE_TEXT = """DRAWDOWN NOTICE

Date: 2025-03-01

To: Lending Agent
From: Demo Borrower Corp

Re: Demo Alpha Term Loan Facility 2025

Dear Sirs,

We hereby give you notice of our intention to make a Drawing under the above
Facility Agreement.

Account Number: 9901
Borrower Account: 9901
Deal ID: (see system)

Utilisation Request Details:

Loan Reference: Demo Alpha Term Loan Facility 2025
Notice of Utilisation

Drawdown Amount: USD 5,000,000
Amount: USD 5,000,000
Currency: USD
Payment Date: 2025-03-05
Value Date: 2025-03-05

Purpose of Utilisation: The proceeds of this drawdown are to be used exclusively
for working capital and general corporate purposes in connection with the Borrower's
core manufacturing operations, consistent with the permitted purpose provisions of
the Facility Agreement.

Please confirm receipt of this notice and the availability of funds.

Yours faithfully,
Demo Borrower Corp
Treasury Department
"""

# ---------------------------------------------------------------------------
# Sample Repayment Notice
# ---------------------------------------------------------------------------

REPAYMENT_NOTICE_TEXT = """REPAYMENT NOTICE

Date: 2025-04-01

To: Lending Agent
From: Demo Borrower Corp

Re: Demo Alpha Term Loan Facility 2025
Loan Reference: Demo Alpha Term Loan Facility 2025

Dear Sirs,

We hereby give notice of our intention to make a voluntary prepayment under the
above Facility Agreement.

Account Number: 9901
Borrower Account: 9901
Currency: USD

Repayment Notice Details:

Repayment Amount: USD 2,000,000
Amount: USD 2,000,000
Payment Date: 2025-04-08
Settlement Date: 2025-04-08

This is NOT a full repayment. The Facility will remain open following this
partial prepayment.

Please confirm receipt and arrange settlement accordingly.

Yours faithfully,
Demo Borrower Corp
Treasury Department
"""

# ---------------------------------------------------------------------------
# Sample Interest Payment Notice
# ---------------------------------------------------------------------------

INTEREST_NOTICE_TEXT = """INTEREST PAYMENT NOTICE

Date: 2025-06-01

To: Lending Agent
From: Demo Borrower Corp

Re: Demo Alpha Term Loan Facility 2025

Dear Sirs,

Interest Payment Notice

We hereby notify you of the following interest payment due under the Facility:

Borrower: Demo Borrower Corp
Account Number: 9901
Borrower Account: 9901
Loan Reference: Demo Alpha Term Loan Facility 2025
Currency: USD

Interest Payment Details:

Total Interest: USD 68,750.00
Interest Amount: USD 68,750.00
Amount: USD 68,750.00

Interest Period Start: 2025-03-05
Period From: 2025-03-05
Interest Period End: 2025-06-05
Period To: 2025-06-05

Principal Amount: USD 5,000,000.00
Amount on which Interest Calculated: USD 5,000,000.00
Notional Amount: USD 5,000,000.00

Applicable Rate: 5.50%
Rate Applied: 5.50%

Payment Date: 2025-06-05

Please confirm receipt.

Yours faithfully,
Demo Borrower Corp
"""

# ---------------------------------------------------------------------------
# Sample Fee Payment Notice
# ---------------------------------------------------------------------------

FEE_NOTICE_TEXT = """FEE PAYMENT NOTICE

Date: 2025-07-01

To: Lending Agent
From: Demo Borrower Corp

Re: Demo Alpha Term Loan Facility 2025

Dear Sirs,

Commitment Fee Notice

We hereby notify you of the following fee payment due under the Facility Agreement:

Borrower: Demo Borrower Corp
Account Number: 9901
Borrower Account: 9901
Loan Reference: Demo Alpha Term Loan Facility 2025
Currency: USD

Fee Payment Details:

Type of Fee: Commitment Fee
Fee Type: Commitment Fee
Amount of Fee: USD 18,750.00
Fee Amount: USD 18,750.00
Total Fee: USD 18,750.00
Amount: USD 18,750.00

Payment Date: 2025-07-05
Value Date: 2025-07-05

This fee is payable in accordance with the Fee Schedule set out in the Facility
Agreement dated 15 January 2025.

Please confirm receipt and arrange settlement.

Yours faithfully,
Demo Borrower Corp
"""


def generate_all() -> None:
    print("Generating sample PDFs...")
    _make_pdf(os.path.join(SAMPLE_DIR, "sample_ca.pdf"), CA_TEXT)
    _make_pdf(os.path.join(SAMPLE_DIR, "sample_drawdown_notice.pdf"), DRAWDOWN_NOTICE_TEXT)
    _make_pdf(os.path.join(SAMPLE_DIR, "sample_repayment_notice.pdf"), REPAYMENT_NOTICE_TEXT)
    _make_pdf(os.path.join(SAMPLE_DIR, "sample_interest_notice.pdf"), INTEREST_NOTICE_TEXT)
    _make_pdf(os.path.join(SAMPLE_DIR, "sample_fee_notice.pdf"), FEE_NOTICE_TEXT)
    print(f"\nDone — 5 PDFs written to {SAMPLE_DIR}")


if __name__ == "__main__":
    generate_all()
