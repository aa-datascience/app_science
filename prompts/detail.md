The text above is the paper ({{source_note}}). The reader has opened this paper in their digest and wants to understand it. Write the detailed entry.

Paper: {{title}}
Authors: {{authors}}
arXiv: {{arxiv_id}} [{{categories}}]
Reader level in this subfield: {{level}}

Figures of the paper, as [label] caption:
{{figures}}

Concepts the reader has already met, as id: name:
{{known_concepts}}

What to produce:
- explanation_lay: 150 to 250 words for an educated non-specialist. No formulas. Explain the physical idea, not the paper's structure.
- explanation_expert: 300 to 500 words for a physics master's student. Give the setup, the method, the key result and how it was obtained, with the essential equations.
- context: what was known before; what this paper changes; its limitations and possible criticisms. Limitations are mandatory: if the authors state none, give the ones a careful referee would raise and say they are yours.
- claims: every factual claim your entry makes about the paper (results, numbers, methods, comparisons with prior work), each with the passage from the paper that supports it.

- figures: one to three figures from the list above that best support your explanation, in the order a reader should look at them. For each, copy its label exactly as it appears in brackets, and write one sentence `what_to_look_at` saying what to notice in it (which curve, which axis, which feature) and what it shows. You can refer to them in the explanations as "Fig. 2". Leave the list empty if no figure is listed.

- concepts: one to three prerequisite concepts a reader needs in order to follow this paper: established physics background, not the paper's own new result. If a concept from the known list above is the same concept, reuse it: copy its id and name exactly and leave both definitions empty. Otherwise create a new one: `id` in lowercase words joined by hyphens (for example "andreev-bound-state"), `name`, `simple_definition` in one or two sentences without formulas, `expert_definition` in two to four sentences at master's level, LaTeX allowed. Never create a new id for a concept that is already in the list under another wording. `related`: ids of up to three closely related concepts, from the known list or from this entry; empty if none.
- questions: two or three comprehension questions whose answer is stated in this paper. They test understanding of the physics and of the result, not trivia such as author names, section or figure numbers. Use `kind` "mcq" with three or four options, one of which is correct, and `answer` copied exactly from that option; or `kind` "short" with `options` empty and `answer` in one sentence. Add an `explanation` of one or two sentences, and a `quote` from the paper that states the answer, following the same rules as the quotes of the claims.

How the quotes are used: a program, not a person, searches for each quote in the paper's text. A claim or question whose quote is not found is deleted, and if too many claims are deleted the whole entry is shown to the reader as unverified. So for each quote:
- Copy it character for character from the text above: one or two consecutive sentences, or part of one sentence. Do not paraphrase, shorten, merge passages, fix typos or use an ellipsis.
- Prefer a passage in plain prose. If the passage contains math, copy the math exactly as it is written above.
- Choose the passage that actually states the claim, so that someone reading only the quote would agree the claim is supported.

Rules, because the reader trusts this entry in place of the paper:
- Every number you write must appear in the paper. Never compute, round differently, or estimate one.
- Keep results apart from what the authors speculate, propose or expect. Say "the authors suggest" when that is what the paper does.
- State only what this text supports. If the text is only the abstract, keep the entry short and do not fill gaps from general knowledge of the field; background that is not from the paper belongs in context.before and in concept definitions only.
- Equations in LaTeX: inline as $...$, display as $$...$$. No other math delimiters, no \begin{equation}.
- Plain prose. No headings or bullet lists inside the fields.
