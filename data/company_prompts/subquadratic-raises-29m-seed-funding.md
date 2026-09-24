# Company Analysis Target: Subquadratic, Inc.

## Overview & Verified Funding Facts
- **Company Name**: Subquadratic, Inc.
- **Website**: https://subq.ai/
- **Domain**: subq.ai
- **Funding Round**: Seed (source: article)
- **Amount Raised**: $29.0M (~$29,000,000 USD-equivalent)
- **Funding Date**: May 2026
- **Lead Investor(s)**: Not specified
- **Additional Investors**: None listed
- **Software Category**: AI Infrastructure / Large Language Models
- **Original Source / Press Release URL**: https://siliconangle.com/2026/05/05/subquadratic-launches-29m-bring-12m-token-context-windows-ai/

## Pricing & Buyer Economics (from Website)
- **Pricing Summary**: No pricing published on website.
- **Sales Model**: Undetermined / hidden

## Funding Article Content
Seed Round
Subquadratic Raises $29M Seed Funding
Subquadratic, a Miami-based AI company developing a novel generative artificial intelligence model, has raised $29 million in Seed funding.
Subquadratic, a Miami-based AI company developing a novel generative artificial intelligence model, has raised $29 million in Seed funding.
Investors
The funding round included investors such as Javier Villamizar, Justin Mateen of JAM Fund, as well as early investors in Anthropic, OpenAI, Stripe, and Brex.
Subquadratic Use of Funds
The company will use the funding to expand development of its SubQ long-context AI model, launch its developer API and coding tools, and scale enterprise AI applications powered by its sparse-attention transformer architecture.
About Subquadratic
Founded by Justin Dangel and Alexander Whedon, Subquadratic is an AI infrastructure company developing a new generation of large language models designed to overcome the scaling limitations of traditional transformer architectures. Its flagship model, SubQ, leverages a proprietary sparse-attention architecture that can handle context windows of up to 12 million tokens. In addition to its API platform, Subquadratic is also developing SubQ Code, a coding agent built for repository-scale AI development tasks. Headquartered in Miami, Florida, Subquadratic's mission is to develop AI that is powerful, trustworthy, and accessible.
Funding Details
Company: Subquadratic, Inc.
Raised: $29.0M
Round: Seed
Funding Date: May 2026
Investors: Javier Villamizar, Justin Mateen (JAM Fund), and early investors in Anthropic, OpenAI, Stripe, and Brex
Company Website:
https://subq.ai/
Software Category: AI Infrastructure / Large Language Models
Source:
https://siliconangle.com/2026/05/05/subquadratic-launches-29m-bring-12m-token-context-windows-ai/

## External Press Release / Source Announcement
Source Title: Subquadratic launches with $29M to bring 12M-token context windows to AI - SiliconANGLE
Source URL: https://siliconangle.com/2026/05/05/subquadratic-launches-29m-bring-12m-token-context-windows-ai/

UPDATED 12:00 EDT / MAY 05 2026
AI
Subquadratic launches with $29M to bring 12M-token context windows to AI
by
Kyt Dotson
Subquadratic
, a company developing a novel generative artificial intelligence model, launched today with $29 million in seed funding.
The new large language model, dubbed
SubQ
, uses what the company calls a subquadratic architecture that greatly increases the context window — how much information the AI can read at once — without significantly increasing the amount of compute it requires. The company also says it outperforms other state-of-the-art models on speed and accuracy.
Many AI systems today are built around the limits of context windows. For example, the industry standard is 128,000 tokens for many AI models and up to 1 million tokens for frontier cloud models such as Claude Sonnet 4.7 and Gemini 3.1 Pro. SubQ can manage a context window of up to 12 million tokens, maintain accuracy, increase speed and reduce compute cost. At that length, it would be around 9 million words, or almost 120 books.
To reach this context size, Subquadratic needed to create a model that could handle that much data without breaking the “compute bank.” To do that, co-founders Justin Dangel, who’s chief executive, and Chief Technology Officer Alexander Whedon told SiliconANGLE in an interview, the company settled on a proprietary transformer architecture that implements sparse attention.
“We are very focused on the problem of how we transition from a dense attention, quadratic scaling architecture to a sparse attention linear architecture,” Dangel said. “Sparse attention is an effort to say, hey, let’s try to figure out how to not compare every token to every token to every token.”
The “T” in ChatGPT stands for “transformer,” which is the type of generative AI model architecture under the hood. It’s not necessary to understand what that is, just that it’s essentially the engine of the LLM that provides its power to contextualize language.
Traditional transformer models use dense attention, meaning the model compares every token in a prompt with every other token. That becomes expensive very quickly: Boubling the input does not just double the work; it roughly quadruples the number of token-to-token relationships the model has to consider. That is the “quadratic” scaling problem Subquadratic is targeting.
Attention
is what transformers use to “understand” how a prompt operates by comparing words (broken up into tokens) to one another. The same way humans know that, in the sentence “The cat is in the room,” the words “cat” and “room” relate to one another, an LLM compares words in a sentence to understand their relationships. With dense attention, every word is compared to every other word. The more words there are, the more comparisons the model needs to make.
“If you double the input size with quadratic scaling laws, you need four times to compute; with linear scaling laws, you need just twice,” Whedon explained.
According to Subquadratic, SubQ is more than 50 times faster and 50 times less expensive than leading frontier models at 1 million tokens, while maintaining higher accuracy. At its full 12 million-token context window, the company says, the model reduces compute requirements by almost 1,000 times compared with other frontier models. On the RULER 128K long-context benchmark, Subquadratic said SubQ scored 95% accuracy at a cost of $8, compared with 94% accuracy and about $2,600 for Claude Opus, representing roughly a 300-times reduction in cost.
Changing context window handling
Currently, the data view of LLMs is limited to a maximum of 1 million tokens for most state-of-the-art models, and even that can be difficult to use because of compute constraints.
To handle this, developers carefully curate the data that goes into the context window using systems such as retrieval-augmented generation, or RAG, and agentic retrieval systems to manage data flow. These systems necessarily add latency and computational overhead, and can bias the information fed to the LLM.
“I used to manually curate prompts and retrieval systems and evals and conditional logic to chain together the workflows,” Whedon said. “And I think that that is kind of a waste of human intelligence and also limiting to the product quality.”
Subquadratic’s vision is that AI is being constrained by the cost curve of dense-attention transformers. The company argues that once the architecture moves from quadratic to linear scaling, developers can build products that were previously too slow, too expensive or too reliant on brittle data curation.
To tackle this, the company is launching the SubQ application programming interface, making it available to developers and enterprise teams that need access to the full 12 million-token context window. It is also launching SubQ Code, a command-line interface coding agent designed to load entire codebases into a single context window, so developers can plan, execute and review across a repository without coordinating multiple agents.
Dangel also described a search product that will initially be free, suggesting a land-and-expand strategy around long-context research, coding and enterprise workloads. He added that the model will not be open-weight or open-source in the near term, but will be trainable for customer-specific use cases.
The funding round was joined by investors including Javier Villamizar, former partner at SoftBank Vision Fund, and Justin Mateen, co-founder of Tinder and founder of JAM fund, alongside early investors in Anthropic PBC, OpenAI Group PBC, Stripe Inc. and Brex Inc.
“The fundamental scaling laws imposed by the transformer architecture and dense attention have been broken through,” Dangel concluded.
Image: SiliconANGLE/Microsoft Designer
A message f

## Scraped Company Website Content
### Subpage: /home
Subquadratic — We build models that scale efficiently.
Products
Research
About
Request Access →
We build frontier models
that scale efficiently
Subquadratic is a frontier AI research company building the most compute-, memory- and sample-efficient algorithms and models.
Request Access →
Read the Research
Introducing SubQ
The best model for
data-intensive workloads.
SubQ is the first model built for
multi-million token reasoning
, allowing enterprises to work across full repositories, financial filings, and contract archives for a fraction of the cost.
Request Access →
Review Benchmarks
Built by researchers and engineers from
The problem
Enterprises are
spending billions
to work around the limitations of today's models.
Token Cost
Context Rot
Latency
Chunking
Embedding
Vector DB
Context Compression
Hallucinations
Eval Patches
Context Drift
Alignment Gaps
Token Cost
Context Rot
Latency
Chunking
Embedding
Vector DB
Context Compression
Hallucinations
Eval Patches
Context Drift
Alignment Gaps
Token Cost
Context Rot
Latency
Chunking
Embedding
Vector DB
Context Compression
Hallucinations
Eval Patches
Context Drift
Alignment Gaps
Use cases
The data-heavy workloads that become
possible.
Whole Artifact Reasoning
Analyze entire datasets at once: an entire GitHub repo, all legal documentation, every vendor contract, or years of SEC filings, without chunking, compression, or context loss.
Long Horizon Agents
Agents that hold the full task in context and remember long sequences of events, collapsing brittle multi-agent orchestration into one coherent run.
Search & Retrieval
Surface material insights that you can trust from across an entire company's IP, code, or documents without risk of hallucination.
All your context.
Always available.
Reason across millions of tokens in one prompt: entire repos, whole artifacts, and long-running agent state, with context to spare.
Tokens
0
12M
Five enterprise vendor contracts
Each a 500-page master agreement
~1.6M
Three years of SEC filings
A Fortune 500 10-Ks and 10-Qs
~2.9M
Python source code
The entire 3.13 standard library
~5.1M
~ Approximate token counts.
The breakthrough
The most
compute
-
efficient
model.
Learn More
Today's transformer-based LLMs waste compute by processing every possible relationship between tokens, but only a small fraction of these relationships matter.
SubQ is built differently. Using a proprietary algorithm called Subquadratic Sparse Attention (SSA), it isolates the tokens and relationships that matter, ensuring compute is used efficiently.
At 2M tokens, SubQ uses
128x less compute
than frontier models.
Benchmarks
A leader in long-context retrieval and reasoning tasks.
Multi-Fact Retrieval
RULER · 128K multi-task retrieval
99.12%
Single Fact Retrieval: 1–2M
Needle-in-a-haystack · 1–2M tokens
100%
Single Fact Retrieval: 6–12M
Needle-in-a-haystack · 6–12M tokens
98%
Benchmark
SubQ 1.1 Small
GPT-5.5
Opus 4.8
Sonnet 4.6
GPT-5.4-mini
GPT-5.4-nano
Haiku 4.5
Graduate-level science
GPQA Diamond · pass@1
85.4
93.2
92
87.5
87.5
81.7
67.2
Agentic finance
AutomationBench
13%
18%
16%
8%
0%
n/r
3%
Competitive programming
LiveCodeBench v6 · pass@4
89.7
92
92.2
88.9
78.6
78.2
69.7
n/r = result not reported by the model provider
Technical report
Early access
Request API Access.
First name
Last name
Company email
Request Access →
By submitting this form, you agree to our
privacy policy
and consent to receive marketing communications from Subquadratic. You can unsubscribe at any time.
Research
From the lab.
Research
June 16, 2026
Introducing SubQ 1.1 Small
Read more →
Partnerships
May 14, 2026
We're Partnering with LayerLens to Evaluate SubQ
Read more →
Product
May 5, 2026
Introducing SubQ: The First Fully Subquadratic LLM
Read more →
Research
Updated
May 15, 2026
How SSA Makes Long Context Practical
Read more →
Building a new class of
LLMs from the architecture up.
Subquadratic
is a frontier AI research company that believes the architecture layer is the highest-leverage surface in AI. While other major labs focus on incremental improvements to Transformer models, we're pushing foundational change at the architecture level to build models and products that scale efficiently.
Built by researchers and engineers from
Product
API
Socials
LinkedIn
X
Discord
Contact
Sales & Enterprise
Press
Legal
Terms of Use
Privacy Policy
Cookies
Acceptable Use Policy
Efficiency is intelligence.
©
2026
Subquadratic Inc.


---
## EVALUATION INSTRUCTIONS & REQUIRED OUTPUT FORMAT
Conduct your complete, brutal, evidence-backed evaluation following all system prompt criteria.
At the very end of your response, you MUST provide a machine-readable JSON code block in this exact schema:
```json
{
  "score": <overall opportunity score as an integer from 0 to 100>,
  "verdict": "<one-sentence executive verdict summarizing why this is or is not a viable agency opportunity>",
  "can_reproduce_48h": <true or false>,
  "agency_tier": "<Tier 1 | Tier 2 | Tier 3 | Disqualified>",
  "primary_risk": "<concise statement of primary business risk>",
  "target_service_offer": "<concise description of the packageable service, or N/A>"
}
```