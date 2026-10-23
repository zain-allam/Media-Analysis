# Broader portrayal sample

Selected 231 source sentences from 30 preprocessed articles. Groups: {'Israel': 84, 'Palestine': 147}. The target is up to five sentences per article per party, with a minimum goal of three. 15 articles meet the minimum for both parties; 15 have at least one shortfall.

## Definition approved in chat

Include factual descriptions, narrator framing, and attributed opinions about each side. Include explicitly pro-Palestinian/pro-Israel movements, with exact targets recorded separately. Never infer pro-Israel affiliation from Jewish identity alone, or treat Hamas/campus groups as equivalent to Palestinian civilians. The original author-opinion-only report is archived as author_opinion_review.html in the previous report folder.

Each selected sentence has a single primary portrayal target. A reference to the other party as speaker, place, recipient, or background is not automatically a second portrayal. Inseparable substantive portrayals of both parties are not selected. Sentences about unrelated people or institutions are not used to fill quotas.

Portrayal values are favorable, critical, neutral, or mixed. Voice values are narration, attributed, or mixed. Quoted claims are not treated as author endorsement or as verified facts. Neutral means no explicit approval/disapproval of the target; civilian suffering can still be the sentence's frame. Exact target_entity, target_type, source_speaker, and frame are provided so this distinction can be checked.

## How the sample was made

The assistant contextually reviewed the retrieved articles and recorded sentence selections and interpretations. This is a purposeful sample, not a random sample, exhaustive labeling of every possible portrayal, or a trained automatic classifier. The script reproduces this fixed set of reviewed decisions for the existing source texts; it cannot automatically classify new articles.

Reported statements and factual descriptions are eligible under the broader task. They are not retrospectively called the author's personal opinions. There is no independent accuracy estimate or calibrated confidence score.

Sentence segmentation now splits multi-sentence quotations and protects common English abbreviations. It retains all original characters other than boundary whitespace. It differs from the earlier S-ID segmentation: use the new T IDs and saved original paragraph context, not the older sentence numbering. Source and sentence hashes support tracing every selected sentence to its extraction.

## Coverage

The prior collection attempted all 78 URLs. Thirty articles passed preprocessing. Forty-eight were blocked, timed out, required extraction review, or were outside the configured research windows. This selection uses those same accepted 30 articles and does not claim to overcome the unavailable sources. The missing NYT/Washington Post articles and purposeful selection prevent reliable general conclusions about comparative publisher bias from this sample alone.

Some campus stories describe student discipline or U.S. institutional decisions but contain few or no distinct Israel-related portrayals. These shortfalls are reported explicitly. No sentence was invented, copied from another article, duplicated within an article, or assigned to both groups to inflate its count.

## Deliverables

- portrayal_review.html: article-by-article report with two groups, filters, sources and shortfalls.
- portrayal_sentences.jsonl / portrayal_sentences.json: all selected sentences and metadata.
- palestine_sentences.jsonl / israel_sentences.jsonl: separate group exports.
- minimum_met_articles.jsonl: only articles with at least three sentences for both party groups; 142 sentences total.
- article_coverage.json: coverage and counts for all 78 URLs.
- sentence_selection_audit.jsonl: source sentence inventory and selection status. Not selected does not mean neither or irrelevant; other eligible sentences may simply remain unsampled.
- summary.json: counts and interpretation rules.
