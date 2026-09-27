# Coverage backlog

What to add next, chosen for the obligations, controls, audit-trail and assurance
questions the register is meant to answer. Tier 1 adds the most new third-party audit
and assurance content. Dates were checked against secondary sources on 2026-09-27 and
must be verified when each entry is added.

## Tier 1: independent audit and assurance regimes

| Instrument | Why | Assurance angle |
|---|---|---|
| **ISO/IEC 42006:2025** (published 7 Jul 2025) | Requirements for bodies that audit and certify ISO/IEC 42001 | Defines what a credible 42001 certification audit looks like |
| **ISO/IEC 42005:2025** (Apr 2025) | How to run an AI system impact assessment | Method behind 42001 cl. 6.1.4, EU AI Act Art. 27, Korea Art. 35 |
| **EN 18286** (CEN-CENELEC, at formal vote mid-2026) | First harmonised standard for the AI Act, covering the Art. 17 QMS | Once cited in the OJ, it gives a presumption of conformity |
| **Other JTC 21 drafts** (risk management, bias prEN 18283, logging, trustworthiness, cybersecurity) | The standards notified bodies will assess against | Track draft to cited status |
| **California CCPA regulations on ADMT, risk assessments and cybersecurity audits** (in force 1 Jan 2026; ADMT from 1 Jan 2027; first audits due Apr 2028 to Apr 2030 by revenue) | Binding, with a mandatory **independent cybersecurity audit** and filings to the CPPA | Audit plus regulator submission |
| **NYC Local Law 144** (automated employment decision tools) | Requires an **independent bias audit** before use, with public results | Classic third-party AI audit |
| **EU Digital Services Act, Art. 34-37** | Systemic-risk assessments for very large platforms, including recommender and generative AI features, with an **annual independent audit** | Detailed audit rules in a delegated regulation |
| **New York RAISE Act** (signed 19 Dec 2025, amended Mar 2026, in force 1 Jan 2027) | Frontier safety frameworks and 72-hour incident reports for large developers | Pairs with California SB 53 in the crosswalk |

## Tier 2: binding laws that shape controls

| Instrument | Why |
|---|---|
| **China AI-generated content Labelling Measures** (in force 1 Sep 2025) and **GB 45438-2025** | Detailed explicit and implicit labelling duties; completes the China picture |
| **China Deep Synthesis and Algorithm Recommendation provisions** | Algorithm filing and security assessment regime the GenAI Measures rely on |
| **EU GDPR Art. 22 and Art. 35 (DPIA)** | Automated decisions and data protection impact assessments for most AI processing personal data |
| **EU Product Liability Directive (EU) 2024/2853** (applies Dec 2026) | Software and AI become products for strict liability; drives documentation and logging |
| **EU Cyber Resilience Act** | Security-by-design and vulnerability handling for products with digital elements, including AI components |
| **Texas TRAIGA (HB 149)**, **Illinois HB 3773**, **Utah AI Policy Act** | State AI laws on disclosure, employment and prohibited uses |
| **Canada Directive on Automated Decision-Making** | Algorithmic Impact Assessment with **peer review** for federal systems |
| **Japan AI Promotion Act (2025)** | Japan's framework law; light-touch but sets government guidance |
| **US OMB AI memoranda for federal agencies** | Minimum risk practices for high-impact federal AI use |

## Tier 3: control catalogues and security frameworks

| Instrument | Why |
|---|---|
| **ISO/IEC 23894:2023** (AI risk management guidance) | Detail behind 42001 risk clauses |
| **ISO/IEC 27001 / 27701** | The security and privacy management systems most AI programmes sit inside |
| **CSA AI Controls Matrix** | Large control catalogue already mapped to 42001 and other frameworks |
| **OWASP Top 10 for LLM Applications**, **MITRE ATLAS**, **NIST AI 100-2** (adversarial ML) | Concrete security controls and threats for Art. 15-style duties |
| **Singapore Model AI Governance Framework and AI Verify** | Testing framework with a public toolkit |
| **G7 Hiroshima Code of Conduct and the OECD reporting framework** | Voluntary frontier-model reporting used by many developers |
| **IEEE 7000 series and IEEE CertifAIEd** | Ethics-by-design process standards and a certification scheme |

## How to add one

1. Add `data/instruments/<id>.yaml` with milestones and sources (see README).
2. Add `requirements`, tagging roles, category, risks, evidence and assurance.
3. Link each requirement to its closest equivalents with `maps_to`.
4. Verify against the official text and set `verified_against: official`.
