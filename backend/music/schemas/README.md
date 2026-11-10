The SEPA credit transfer exporter (`music/payouts.py`) validates pain.001.001.09 in two steps:

1. Against the unmodified ISO 20022 original schema `pain.001.001.09.xsd`
   (Customer Credit Transfer Initiation V09) from the ISO 20022 message catalogue,
   https://www.iso20022.org, used under the ISO 20022 terms of use and IPR policy
   (https://www.iso20022.org/terms-use, https://www.iso20022.org/intellectual-property-rights).
2. Against the stricter rules of the German banking industry (DK, GBIC 5) in code:
   `music.payouts.dk_rules` (SEPA character set and lengths, EUR only with two decimals,
   service level SEPA, charge bearer SLEV, consistent counts and control sums).

The DK technical validation subset (GBIC 5) itself is no longer part of the repository,
because no permission to redistribute that file was documented (licence audit 2026-11-10, L04).

Schema validation cannot establish bank acceptance, execution or payee ownership.
Users must check the file and approve it separately at their bank.
