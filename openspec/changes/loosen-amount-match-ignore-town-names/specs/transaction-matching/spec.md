# Spec Delta

## Purpose

Matches each complaint to the single debit it refers to, using the clues the customer gave (amount, date, card, merchant or payee name), so the decision and refund are made about the right transaction.

## ADDED Requirements

### Requirement: Hedged amount tolerance
When the customer gives a hedged amount ("about", "around", "dalam", "lebih kurang", "kira-kira"), a debit SHALL stay a candidate only if its amount is within 20% of the stated amount, inclusive. A debit further off SHALL NOT be matched.

#### Scenario: Hedged amount 7% off stays a candidate
- **WHEN** a complaint says "dalam RM100" and the customer has a matching-category debit of RM107.13 to the named payee on the named date
- **THEN** that debit is a candidate and is matched

#### Scenario: Hedged amount exactly 20% off stays a candidate
- **WHEN** a complaint says "about RM100" and the only matching-category debit is RM120.00
- **THEN** that debit is a candidate

#### Scenario: Hedged amount over 20% off is excluded
- **WHEN** a complaint says "about RM100" and the only matching-category debit is RM123.25
- **THEN** that debit is not matched and the result is no match

### Requirement: Exact amount must match to the cent
When the customer gives an amount without a hedge word, a debit SHALL stay a candidate only if its amount equals the stated amount to the cent.

#### Scenario: Unhedged amount one cent off is excluded
- **WHEN** a complaint says "RM227.11" and the debit is RM227.12
- **THEN** that debit is not a candidate

### Requirement: Closer hedged amounts rank higher
Among candidates within the hedged-amount tolerance, a debit whose amount is closer to the stated amount SHALL score higher than one further away, when all other clues are equal.

#### Scenario: Two candidates differ only in amount
- **WHEN** a complaint says "about RM100" and two otherwise identical debits are RM101.00 and RM115.00
- **THEN** the RM101.00 debit scores higher

### Requirement: Town names are not name evidence
A word in a merchant or payee name that is a customer town or city name (from the customer data) SHALL NOT, on its own, count as the complaint naming that merchant or payee.

#### Scenario: Shop shares only the town with the complaint
- **WHEN** a complaint mentions "Butik Ayu Melaka" and a candidate debit is at "Kedai Buku Ilmu Melaka"
- **THEN** that candidate gets no name credit

#### Scenario: Shop-identifying word still counts
- **WHEN** a complaint mentions "Butik Ayu Melaka" and a candidate debit is at "Butik Ayu Melaka"
- **THEN** that candidate gets name credit

#### Scenario: Extracted payee name still counts in full
- **WHEN** the extracted payee is "Melaka Station" and a candidate debit's merchant is "Melaka Station"
- **THEN** that candidate gets name credit
