<!-- markdownlint-disable MD033 -->
# <Paper Title>

## <Subtitle (Optional)>

<Author Names>
<Affiliations>
<Contact Emails>

---

## Abstract

<Abstract text summarizing the motivation, methodology, models evaluated, key results, and conclusions.>

---

## Keywords

<Keywords; e.g., LLM agents, benchmarking, cost-of-pass, multi-agent systems, software engineering>

---

## 1. Summary

<High-level executive summary of the research goals, experimental setup, major findings, and implications.>

---

## 2. Introduction

<Problem statement and motivation.>
<Background on LLM agents and agentic architectures.>
<Research questions and hypotheses.>
<Contributions of this paper.>

---

## 3. Related Work

<Prior work on LLM benchmarking.>
<Related work on agentic systems and multi-agent architectures.>
<Existing evaluation frameworks and gaps addressed by this work.>

---

## 4. Test Methodology

### 4.1 Experimental Design

<Overall experimental design and rationale.>
<Ablation strategy and tiered evaluation approach (T0–T6).>

### 4.2 Dimensional Search Space

<Definition of dimensional axes explored in this study.>

* **Agent Complexity:** <Tier 0–6 definition and criteria>
* **Prompt Complexity:** <Prompt scale 0–10 definition>
* **Skill Complexity:** <Definition and categorization>
* **Agent Hierarchy:** <Flat vs hierarchical vs hybrid>

---

## 5. Test Metrics

### 5.1 Performance Metrics

<Completion metrics, success rates, and accuracy definitions.> <Fine-grained progress metrics.>

### 5.2 Quality Metrics

<Implementation rate, semantic correctness, and validation strategy.> <Code quality and maintainability metrics.>

### 5.3 Efficiency and Cost Metrics

<Latency measurements.>
<Token usage and cost accounting.>
<Cost-of-Pass (CoP) definition and calculation.>

---

## 6. Test Configuration

### 6.1 Hardware and Infrastructure

<Compute environment, hardware specifications, and execution environment.>

### 6.2 Software Stack

<Frameworks, libraries, orchestration tools, and evaluation harness.>

### 6.3 Model Configuration

<Model versions, context limits, decoding parameters, and safety settings.>

---

## 7. Test Cases

### 7.1 Pull Request (PR) Selection Criteria

<Selection methodology and constraints.>

* **PR Size Categories:**

  * <Small: < 100 LOC>
  * <Medium: 300–500 LOC>
  * <Large: 500–2000 LOC>

### 7.2 Workflow Categories

<Description of each workflow category and evaluation intent.>

* **Build System:** <Description>
* **CI/CD:** <Description>
* **Bug Fixing:** <Description>
* **New Features:** <Description>
* **Refactoring:** <Description>
* **Optimization:** <Description>
* **Review:** <Description>
* **Documentation:** <Description>
* **Issue Filing:** <Description>

### 7.3 Test Case Matrix

<Table mapping PRs × workflow categories × complexity tiers.>

---

## 8. Model Summary

### 8.1 Claude Code Models

* **Claude Opus:** <Model description and role>
* **Claude Sonnet:** <Model description and role>
* **Claude Haiku:** <Model description and role>

### 8.2 OpenAI Models

* **Codex / GPT‑5.2:** <Model description and role>

### 8.3 Large Model CLI-Based Systems

<Unified description of CLI-based or tool-driven agent systems.>

* **Claude Opus:** <Details>
* **OpenAI GPT‑5.2:** <Details>
* **Gemini 3.0 Pro:** <Details>
* **DeepSeek:** <Details>
* **Qwen 3:** <Details>
* **MBZ‑K2:** <Details>
* **Kimi‑K2 + Kimi‑3:** <Details>

---

## 9. Results

### 9.1 Quantitative Results

<Tables and figures summarizing performance, quality, and cost metrics.>

### 9.2 Comparative Analysis

<Comparison across models, tiers, and workflow categories.>

### 9.3 Cost–Performance Trade-offs

<Analysis of CoP, scaling behavior, and diminishing returns.>

---

## 10. Discussion

<Interpretation of results.>
<Implications for agent design and deployment.>
<Observed failure modes and limitations.>

---

## 11. Conclusions

<Summary of findings.>
<Answers to research questions.>
<Key takeaways for practitioners and researchers.>

---

## 12. Further Work

<Proposed extensions, additional benchmarks, and future research directions.>

---

## Acknowledgements

<Acknowledgements and funding sources.>

---

## References

<Bibliography entries in the required citation format.>

---

## Appendices

### Appendix A: Detailed Metric Definitions

<Expanded definitions and formulas.>

### Appendix B: Additional Tables and Figures

<Supplementary results.>

### Appendix C: Reproducibility Checklist

<Steps, configurations, and artifacts required to reproduce the study.>
