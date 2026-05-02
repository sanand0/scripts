---
name: data-analysis
description: Use to investigate data for surprising, actionable insights
---

# Investigative Data Analysis

Hunt for stories that make smart readers lean forward and say _"wait, really?"_ - findings that are high-impact, surprising, actionable, and defensible.

This is a DETAILED process. Create a PLAN and execute step by step.

## 1. Define What Matters

- Who are the audiences and what are their key questions?
- What decisions could findings actually inform? What's actionable vs. merely interesting?
- What would _contradict conventional wisdom_ or reveal hidden patterns?

## 2. Understand the Data

- **Structure**: Dimensions (categorical) vs. measures (numeric), types, granularity, field relationships.
- **Quality**: Completeness, missing values, outliers, duplicates, encoding issues.
- **Distribution**: Value ranges, (log) normality, skewness, heavy tails, zero-inflation.
- **Derived potential**: Computable metrics (features, targets), joins, aggregations, time-series constructions.

## 3. Hunt for Signal

Apply diverse **analysis toolkits** ranging from statistical tests to geospatial, network, NLP, time series, cohort, segmentation, survival analysis, etc. to expand the insights pool.

Look for stories that _confirm something suspected but never proven_, or _overturn something everyone assumes is true_:

- **Extreme/unexpected distributions**: What's at the tails? What shouldn't be there?
- **Pattern breaks**: Where does a trend suddenly shift? What changed, and when?
- **Surprising correlations**: What moves together that shouldn't? What's independent that should correlate?
- **Standout entities**: Who dramatically overperforms or underperforms relative to peers? Who drives trends vs. bucks them?
- **Hidden populations**: What patterns disappear in aggregate but emerge in subgroups? (Watch for Simpson's Paradox.)
- **Dot connections**: What patterns emerge when combining fields that seem unrelated at first?
- **Clusters**: What clusters or communities emerge? Where are the overlaps and outliers?

Search internally / externally:

- Discover domain-specific rules, context, that have an impact
- Search for WHY this happened
- Surface confounders
- Explore prior research

Find leverage points:

- Underutilized resources or capabilities
- **Phase transitions**: thresholds where behavior shifts nonlinearly
- **Tipping points**: what small change would move the aggregate needle?
- What actions are _specific and implementable_, not just directionally correct?

## 4. Verify & Stress-Test

**Cross-check externally**: Is there outside evidence (benchmarks, research, industry data) that supports, refines, or contradicts the finding?

**Test robustness**: Does the finding hold under cross model checks, alternative model specs, thresholds, sub-samples, or time windows? Does a placebo test (shuffled labels, random baseline) reproduce it? If so, it's noise.

**Check for errors & bias**: Examine data provenance, definitions, collection methodology. Control for confounders, base rates, uncertainty. What's _missing_? Selection and survivorship bias are silent killers.

**Check for logical fallacies**:

- **Correlation vs. causation**: is there a plausible mechanism, or just co-movement?
- **Goodhart's Law**: is the metric gamed? Does measuring it change behavior?
- **Simpson's Paradox**: does segmentation flip the trend?
- **Regression to the mean**: are extreme values just natural variation reverting?
- **Occam's Razor**: is there a simpler explanation you're overlooking?
- **Survivorship/selection bias**: what's missing from the data entirely?
- **Second-order effects**: what happens downstream beyond the immediate impact?
- **Inversion**: try to _disprove_ the finding. If you can't, it's more credible.

**Consider limitations**: What _cannot_ be concluded? What caveats must accompany the finding to avoid misuse?

## 5. Prioritize & Package

Select insights that are

- **high-impact** (meaningful effect sizes vs. base rates, not incremental),
- **actionable** (specific and implementable, not just "invest more in X"),
- **surprising** (challenges assumptions, reveals hidden patterns), and
- **defensible** (robust under scrutiny, bias-checked).

Lead with the most compelling finding → evidence → caveats → what to _do_ with it.

**Tone**: Write like a journalist, not a statistician. Say "Sales reps in the Northeast close 2x faster, but only for deals under $10K", not "Closure varies by region." Findings should make a smart reader lean forward.
