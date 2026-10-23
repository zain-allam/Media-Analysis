# Sentence classification run

Requested: 78 articles. Classified: 30. Reviewed: 984 sentences. Retained: 6 sentences.

## Inclusion rule

The assistant reviewed the retrieved article text in context and recorded proposed sentence-level labels. A sentence is retained only if it contains narrator evaluation or interpretive framing directed at exactly one side. Reporting an event, mentioning a party, describing documented harm, or quoting a critical source does not automatically qualify. Sentences about neither and evaluations of both are excluded from the retained groups. Narrator framing is not a claim about personal beliefs.

The Palestine label covers Palestinian actors, with target_entity identifying the organization or population concerned. Opinions about Hamas are not treated as opinions about all Palestinians. Jewish identity does not imply an Israeli political affiliation. Evaluations of U.S. solidarity/protest movements are excluded from the direct party groups and saved separately in movement_related_candidates.jsonl (28 sentences). Hostility toward a protest movement does not establish hostility toward Palestine.

These are proposed LLM annotations, not independently validated ground truth. They include mild rhetorical framing and a few flagged interpretive boundary cases. No numerical confidence or model accuracy is claimed. Category sizes were not forced to balance. Zero qualifying sentences in a news report is a valid result.

## Collection and preprocessing

The run invoked the existing repository's scrape_article and process_raw_dataset functions under Python 3.12. A wrapper retrieved accessible DOM bodies to restore real paragraph boundaries, excluded non-article blocks and headings, and checked their overlap with the extracted article text. The original publication dates, article identities, hashes, configured research windows, and strict admission checks were preserved. There is no paywall bypass in this run.

All 78 URLs were attempted. See article_coverage.json and articles_excluded.csv for missing or excluded articles. New York Times pages returned access-denied HTTP responses; Washington Post requests timed out. Four Fox extractions needed metadata review. Three successfully extracted CBS articles fell outside the configured research windows. The accepted sample therefore cannot establish an overall comparison across all four publishers.

## Files

- sentence_review.html: readable, searchable retained results and article coverage.
- sentences_palestine.jsonl and sentences_israel.jsonl: retained sentence groups.
- sentences_retained.jsonl: both retained groups with explanations and source sentence IDs.
- sentences_all_audit.jsonl: all sentence decisions, including excluded cases.
- movement_related_candidates.jsonl: evaluations of protest movements, excluded from the two direct party groups.
- article_coverage.json: status and counts for each of the 78 URLs.
- articles_processed.json: preprocessor output with raw and cleaned representations.
- summary.json: counts and rules.

Sentence IDs identify positions in this extraction, not immutable paragraph numbers on a publisher webpage. The output retains original casing for classification; source text was not classified using its lowercased analysis representation. The build script replays these reviewed decisions for this corpus; it does not classify new articles automatically.
