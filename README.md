# Pulse - an uptime bond that is forfeited only after the contract itself has seen the address fail, repeatedly

A GenLayer Intelligent Contract for service-level bonds. A provider stakes an
amount behind a public health URL, names the person it owes if the service is
not up (the beneficiary), and sets how many failed probes **in a row** count as
a breach and how far apart probes must be. Anyone may probe. A probe is made by
**the contract itself**: it fetches the URL, reads the HTTP status, and when the
page answers it has the validators read the page and say whether it reports a
healthy service or a failing one. The contract counts. Enough failed probes in a
row and the whole stake goes to the beneficiary at once. A healthy probe wipes
the count. When the term ends without a breach, the stake goes back to the
provider.

- **Contract:** [`packages/contracts/pulse.py`](packages/contracts/pulse.py)
- **Tests:** `pnpm test` (or `python -m pytest packages/contracts/tests -q`): nothing to install but `pytest`
- **Mutation pass:** `python packages/contracts/scripts/mutate.py`
- **Deployed:** see [It is live](#it-is-live-and-every-path-is-on-chain) below, and [`packages/contracts/deployments/studionet.json`](packages/contracts/deployments/studionet.json)
- **Verify a deployment:** `pnpm verify:contract` - reads the source back off chain, diffs it with this file and lints those bytes
- **License:** MIT

---

## It is live, and every path is on chain

<!-- measured:deployment:start -->
Deployed on studionet at [`0x7477Ac71C83987328De285BAa868C37c1EC6b0dc`](https://explorer-studio.genlayer.com/address/0x7477Ac71C83987328De285BAa868C37c1EC6b0dc) (deploy [`0x8310c7bc...`](https://explorer-studio.genlayer.com/tx/0x8310c7bc10d0393485702e6d7f24d4c0de34aef795a2379bc0aac4aa3e5d7658)). Every value below was read back from the chain by `pnpm demo:contract` and written to [`deployments/studionet.json`](packages/contracts/deployments/studionet.json); none of it is typed by hand. The three health addresses are files in this repository: [`healthy`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/healthy.txt), [`gone`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/gone.txt), [`degraded`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/degraded.txt) (`gone` was never committed, so it answers 404).

| Bond | Health address | Strikes needed | Probes | Worst run | Status | Stake |
|---|---|---|---|---|---|---|
| 0: Orders API, healthy | [`demo/healthy.txt`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/healthy.txt) | 2 | 2 | 0 | **kept** | 0.05 GEN |
| 1: Orders API, address gone | [`demo/gone.txt`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/gone.txt) | 2 | 2 | 2 | **breached** | 0.05 GEN |
| 2: Orders API, in maintenance | [`demo/degraded.txt`](https://raw.githubusercontent.com/Elinajafari/pulse/main/demo/degraded.txt) | 2 | 1 | 1 | **kept** | 0.05 GEN |

Every probe, and what the contract made of it:

| Bond | Probe | State | Status class | Strikes after | Reason the leader gave (not consensus) |
|---|---|---|---|---|---|
| 0 | 1 | **up** | 2xx | 0 | The page reports status ok, all systems operational, p95 latency of 120 ms, and no incidents this month. Nothing indicates degradation, down |
| 0 | 2 | **up** | 2xx | 0 | The fetched page explicitly states the status is ok and all systems operational. |
| 1 | 1 | **down** | 4xx | 1 | the address answered 4xx |
| 1 | 2 | **down** | 4xx | 2 | the address answered 4xx |
| 2 | 1 | **down** | 2xx | 1 | Page states status is maintenance and service is unavailable. |

StudioNet charges a fee on every write, so a wallet's balance alone cannot show what it was paid. What each wallet received is read from the chain's own index: the transfers the contract sent it, against what the contract says it sent:

| Wallet | Received from the contract | The contract sent | Transfer |
|---|---|---|---|
| provider | 0.1 GEN | 0.1 GEN | [`0x4018c120...`](https://explorer-studio.genlayer.com/tx/0x4018c1209c90f7c2699d17c6bf638e884153fe9a73999e76fd2a6ab4744670b6), [`0x40800ac0...`](https://explorer-studio.genlayer.com/tx/0x40800ac0b9749193b44096987fd8d8236a6f50b9071cc486b88a169f4546911a) |
| beneficiary | 0.05 GEN | 0.05 GEN | [`0xaaab3a54...`](https://explorer-studio.genlayer.com/tx/0xaaab3a54571219a40ba32cfc1494ef6ed47523832dedc86375617d6b1f8fccbd) |

Held by the contract afterwards: 0 wei.

Every transaction, in order, refusals included, with the wallet that sent it:

| Step | From | Outcome | Transaction |
|---|---|---|---|
| bond 0 opened: a healthy address, 2 failed probes in a row are a breach | provider | ok | [`0xa0c82d04...`](https://explorer-studio.genlayer.com/tx/0xa0c82d0475a1eed4b8f07f56bfb4f71bd473f73ed1c9b4475522c261e9ef647d) |
| bond 1 opened: an address that answers 404 | provider | ok | [`0x90fee80c...`](https://explorer-studio.genlayer.com/tx/0x90fee80c82caef9fc92491f2cce2b50edce9018e47af03932aaa82f8ba0e4f46) |
| bond 2 opened: an address that answers 200 and says it is down | provider | ok | [`0x25af2063...`](https://explorer-studio.genlayer.com/tx/0x25af2063edd3ed704f71ef92d4c556081377a87373a5f65a87f208aec5710579) |
| bond 0, probe 1: the page answers 200 and reads healthy: up | stranger | ok | [`0xe2538fb7...`](https://explorer-studio.genlayer.com/tx/0xe2538fb738e54ad44885367eebde1a9a554a928271edb062cea9e38935853a53) |
| bond 0: a probe sooner than the gap: refused | stranger | refused: the next probe is allowed at 2026-11-23T22:39:38Z | [`0x1cc38e43...`](https://explorer-studio.genlayer.com/tx/0x1cc38e435e81e9c45055118c318cef27d71d41ca9a62f4f93c5997193baeb3a9) |
| bond 1, probe 1: the address answers 404: down, strike 1 | stranger | ok | [`0xcfb2456d...`](https://explorer-studio.genlayer.com/tx/0xcfb2456df1a66102e46ba047a5f9edbdb3d72a1c928dd7ae49a45dd73e039791) |
| bond 2, probe 1: 200 but the page says maintenance: down, strike 1 | stranger | ok | [`0x3ba27718...`](https://explorer-studio.genlayer.com/tx/0x3ba2771874c0405902d6763e8145c6bb244ab93fc352531d63e4ca537b19a1f1) |
| bond 0, probe 2: healthy again: up | stranger | ok | [`0x7f94a643...`](https://explorer-studio.genlayer.com/tx/0x7f94a643cc9c2328a859f3948d51e1c5680c49ed37b5d31267d8d5ab69de60ec) |
| bond 1, probe 2: 404 again: strike 2, the bond is breached and the stake is paid out | stranger | ok | [`0x013868bc...`](https://explorer-studio.genlayer.com/tx/0x013868bcfb1d82b8ea67b613379a82bfa7d614918827c07cd137e730b84b0a0d) |
| a probe on a breached bond: refused | stranger | refused: this bond is breached; only an open one is probed | [`0x9aea3084...`](https://explorer-studio.genlayer.com/tx/0x9aea3084d80a1bc4c1e2f10f6d0860412585e8c6a7be7982c55fd513dcb5b840) |
| a settlement while bond 0's term is still running: refused | stranger | refused: the term runs until 2026-11-23T22:44:58Z | [`0x608179d2...`](https://explorer-studio.genlayer.com/tx/0x608179d2276259002c75a2c65413a8028d6718cb1ab2fc0ab049de2da6b3ce28) |
| bond 2 settled: only one failure, never a breach: the stake returns to the provider | stranger | ok | [`0xa5aefbc5...`](https://explorer-studio.genlayer.com/tx/0xa5aefbc5680e532a6eec4962c73dec20bf99fa69e138edc950a91dd2154f1768) |
| bond 0 settled: never breached: the stake returns to the provider | stranger | ok | [`0x78682eff...`](https://explorer-studio.genlayer.com/tx/0x78682effd2d188b2d2daedcb0d0f50012ec04ff13d015a24a1b0586bb858ee9f) |
| a settlement of a breached bond: refused | stranger | refused: this bond is breached; nothing to settle | [`0xa9fb81a4...`](https://explorer-studio.genlayer.com/tx/0xa9fb81a4922cfe3d67ebaf1be6388ef1543ec421f17e08ddfc54a0e49f3f51f4) |
<!-- measured:deployment:end -->

## The problem

An uptime promise is easy to make and hard to enforce. The customer says the
service was down, the provider says it was up, and nobody can prove either. A
bond released on the customer's word is released to anyone who says so.

A bond released only after **the contract has watched the service fail, several
times, apart in time**, cannot be claimed by assertion, and a provider cannot
talk its way out of what the contract saw.

## How consensus is used

### Before any address is fetched, and before any model

The contract refuses for free what no probe could change: a probe on a bond that
is already settled, a probe after the term ended, a probe sooner than the agreed
gap after the last one, and a bond that has taken all 200 probes it will.

### The probe

The block fetches the address with `gl.nondet.web.get`, independently on the
leader and on each validator, and reads the HTTP status. **Anything but 2xx, and
any fetch that fails, is `down` without asking a model.** A page that answers
2xx is read by the model, which picks one of two options the contract wrote,
`healthy` or `failing`, asked in both orders and read back through the order it
was asked in. The same option both ways stands; **anything else is `unclear`**,
and so is an empty page. `unclear` changes nothing: no strike, no reset.

The block returns the state and the status *class* (`2xx`, `3xx`, `4xx`, `5xx`,
`none`). A 502 and a 503 are the same failure; a 404 is a different one. The
validator agrees only when both match its own exactly.

### The validator, in two layers

1. **Structural, and free.** A known state with a known class, and a state that class can produce (`up` and `unclear` need a 2xx).
2. **Exact agreement**, after the validator has fetched the address and read the page itself.

A model answer that is unusable is retried once and then raised as `[LLM_ERROR]`,
which no validator agrees with, so a broken model can never record a strike.

## What the contract decides, not the model

| reading | strikes | |
|---|---|---|
| `down` | +1 | not 2xx, a failed fetch, or a 2xx page that reads as failing |
| `up` | back to 0 | a 2xx page that reads as healthy |
| `unclear` | unchanged | an empty page, or a page that reads differently in the two orders |
| breach | | `strikes >= strikes_needed`: the whole stake to the beneficiary |

Counting, the gap between probes, the breach and the payment are the contract's
own arithmetic. The model only ever says whether one page it was shown looks
healthy.

## The state machine and its clock

```
open --(strikes reach the threshold)--> breached   (stake to the beneficiary)
open --(term ends, settle)--> kept                 (stake back to the provider)
```

`deadline = open + term`; `next probe = last probe + gap`.

## Who may write

| Method | Who | Why |
|---|---|---|
| `open(beneficiary, title, url, gap, strikes_needed, term)` payable | anyone | the caller is the provider |
| `probe(id)` | anyone | the bond only ever moves on what the contract itself reads, so who asks does not matter; the caller is recorded |
| `settle(id)` | anyone | the stake goes back to the recorded provider, only after the term; it reads no page and no model |

## Running the tests

```bash
pip install -r packages/contracts/requirements-dev.txt
python -m pytest packages/contracts/tests -q
python packages/contracts/scripts/mutate.py
```

<!-- measured:tests:start -->
Measured: **114 passed**.
<!-- measured:tests:end -->

### The tests have teeth

<!-- measured:mutations:start -->
Measured: **85 mutations, 85 caught, 0 escaped.**

| Mutation | Caught by |
|---|---|
| a 2xx status is not a 2xx | `test_a_status_is_read_as_its_class` |
| a 3xx status is a success | `test_a_status_is_read_as_its_class` |
| a 4xx status is a 5xx | `test_a_status_is_read_as_its_class` |
| a status that is not a number is read | `test_a_status_is_read_as_its_class` |
| an option past the list is accepted | `test_an_answer_is_an_option_number_and_nothing_else` |
| an answer in words is read as a number | `test_an_answer_is_an_option_number_and_nothing_else` |
| the second pass is asked in the forward order | `test_a_2xx_page_is_read_in_both_orders_by_the_leader_and_the_validator` |
| the reversed order is not reversed | `test_the_options_follow_the_order` |
| a disagreement between the orders is up | `test_a_page_has_to_read_the_same_both_ways_to_count` |
| a disagreement between the orders is down | `test_a_page_has_to_read_the_same_both_ways_to_count` |
| failing is read as up | `test_a_page_has_to_read_the_same_both_ways_to_count` |
| an answer is not read back through its order | `test_the_options_follow_the_order` |
| an unusable answer is not retried | `test_an_unusable_answer_is_an_error_and_never_a_reading` |
| an unusable answer is read as healthy | `test_an_unusable_answer_is_an_error_and_never_a_reading` |
| an answer that is not an object crashes the block | `test_an_unusable_answer_is_an_error_and_never_a_reading` |
| a failed fetch is not down | `test_a_5xx_and_a_failed_fetch_are_down_too` |
| a status that is not 2xx is not down | `test_a_page_that_does_not_answer_2xx_is_down_without_asking_a_model` |
| a status that is not 2xx still asks the model | `test_a_page_that_does_not_answer_2xx_is_down_without_asking_a_model` |
| an empty page is read as up | `test_an_empty_page_is_unclear_and_asks_no_model` |
| an empty page is read as down | `test_an_empty_page_is_unclear_and_asks_no_model` |
| an empty page is still read by the model | `test_an_empty_page_is_unclear_and_asks_no_model` |
| the address is never actually fetched | `test_a_healthy_page_is_up_and_changes_nothing_else` |
| the validator agrees with an error | `test_an_unusable_answer_is_an_error_and_never_a_reading` |
| the validator skips the structural check | `test_a_leader_that_sends_an_unsound_reading_is_refused_before_any_prompt` |
| the validator agrees with anything sound | `test_nodes_that_read_the_status_differently_do_not_agree` |
| the validator agrees when its own fetch or model fails | `test_a_validator_whose_own_model_fails_does_not_agree` |
| agreement ignores the class | `test_agreement_is_exact_symmetric_and_over_sound_readings` |
| agreement ignores the state | `test_agreement_is_exact_symmetric_and_over_sound_readings` |
| agreement ignores soundness | `test_agreement_is_exact_symmetric_and_over_sound_readings` |
| an unknown state is sound | `test_the_structural_check` |
| an up reading may come from any class | `test_the_structural_check` |
| an unclear reading may come from any class | `test_the_structural_check` |
| a down adds no strike | `test_a_down_adds_a_strike_an_up_clears_them_and_an_unclear_changes_nothing` |
| an up does not clear the strikes | `test_a_down_adds_a_strike_an_up_clears_them_and_an_unclear_changes_nothing` |
| an unclear clears the strikes | `test_a_down_adds_a_strike_an_up_clears_them_and_an_unclear_changes_nothing` |
| a breach needs one strike too many | `test_a_breach_is_the_threshold_exactly` |
| one strike is a breach | `test_a_breach_is_the_threshold_exactly` |
| the agreed reading is not checked again | `test_the_contract_does_not_trust_a_consensus_value_it_cannot_read` |
| the strike count is not stored | `test_a_page_that_reads_one_way_in_one_order_is_unclear_and_changes_nothing` |
| the worst run is not tracked | `test_consecutive_failures_are_counted_and_a_healthy_probe_clears_them` |
| the strikes after a probe are recorded wrongly | `test_a_page_that_does_not_answer_2xx_is_down_without_asking_a_model` |
| the probe time is not recorded | `test_the_gap_a_bond_was_opened_with_is_the_gap_it_enforces` |
| probes are not linked | `test_a_5xx_and_a_failed_fetch_are_down_too` |
| the probe count is not raised | `test_a_healthy_page_is_up_and_changes_nothing_else` |
| a leader's reason is stored as sent | `test_a_leader_s_reason_is_stored_clean_and_capped_even_if_the_validator_never_saw_it` |
| a leader's reason is stored uncapped | `test_the_reason_is_sanitised_and_capped` |
| a breach pays the provider | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| a breach pays nobody | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| a breach pays less than the stake | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| a breach does not mark the bond breached | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| a breach does not record when | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| a probe is taken on a bond that is not open | `test_a_breached_bond_takes_no_more_probes_and_does_not_settle` |
| probes never close | `test_a_probe_after_the_term_is_refused_and_the_last_moment_is_not` |
| a bond takes any number of probes | `test_a_bond_takes_a_bounded_number_of_probes` |
| a probe may come sooner than the gap | `test_the_gap_a_bond_was_opened_with_is_the_gap_it_enforces` |
| the gap is exclusive | `test_the_gap_is_inclusive_and_the_first_probe_is_never_too_soon` |
| the first probe is too soon | `test_the_gap_is_inclusive_and_the_first_probe_is_never_too_soon` |
| the gap is ignored after the first probe | `test_the_gap_is_inclusive_and_the_first_probe_is_never_too_soon` |
| a bond settles while the term runs | `test_nothing_settles_while_the_term_runs` |
| a breached or kept bond settles again | `test_a_breached_bond_takes_no_more_probes_and_does_not_settle` |
| settle pays the beneficiary | `test_a_bond_that_was_never_breached_returns_the_stake_to_the_provider` |
| settle returns nothing | `test_a_bond_that_was_never_breached_returns_the_stake_to_the_provider` |
| settle is not recorded | `test_a_settled_bond_takes_no_more_probes` |
| a stake of nothing is accepted | `test_everything_else_is_bounded` |
| the held counter is not raised | `test_a_bond_opens_with_its_terms_frozen_and_the_stake_held` |
| a payout beyond what is held is sent | `test_a_payout_beyond_what_is_held_is_refused` |
| the held counter is not lowered | `test_enough_failures_in_a_row_pay_the_whole_stake_to_the_beneficiary_at_once` |
| the provider may name itself as the beneficiary | `test_the_beneficiary_must_be_an_address_and_not_the_provider` |
| the beneficiary need not look like an address | `test_the_beneficiary_must_be_an_address_and_not_the_provider` |
| the address is not checked | `test_everything_else_is_bounded` |
| an address with angle brackets is accepted | `test_a_fetchable_address` |
| the gap is unbounded | `test_everything_else_is_bounded` |
| the number of strikes is unbounded | `test_everything_else_is_bounded` |
| the term is unbounded | `test_everything_else_is_bounded` |
| the term does not set the clock | `test_a_bond_opens_with_its_terms_frozen_and_the_stake_held` |
| the number of strikes is not stored | `test_consecutive_failures_are_counted_and_a_healthy_probe_clears_them` |
| the gap is not stored | `test_the_gap_a_bond_was_opened_with_is_the_gap_it_enforces` |
| the title is unbounded | `test_everything_else_is_bounded` |
| the fence is removed | `test_the_fence_replaces_and_preserves_length` |
| the fence leaves square brackets | `test_the_fence_replaces_and_preserves_length` |
| the fetched page reaches the prompt unfenced | `test_hostile_page_content_cannot_close_a_block_or_forge_an_option` |
| the service name reaches the prompt unfenced | `test_hostile_page_content_cannot_close_a_block_or_forge_an_option` |
| a whole page, however long, reaches the prompt | `test_only_the_first_part_of_a_long_page_is_shown` |
| the prompt lets the model guess | `test_the_prompt_judges_what_the_page_says_and_nothing_else` |
| control characters are stored | `test_clean_text_collapses_whitespace_and_control_characters` |
<!-- measured:mutations:end -->

## Design rules applied

- **The coarsest answer that carries the judgment.** Status classes and one of three states cross consensus; the reason sentence is display only.
- **Uncertainty goes in the value.** `unclear` is its own state with its own rule: it changes nothing.
- **Both presentation orders** for every page the model reads.
- **The contract counts, not the model:** strikes, resets, gaps and the breach are arithmetic.
- **Every write is bound to an address**, and a test fails when a write is added without being classified.
- **Untrusted text is fenced** at the prompt boundary, and a test fails when a prompt value is not.
- **The deployed bytes are the repository's bytes:** `pnpm verify:contract`.

## Known limits

- A probe is a single moment: a service that fails between probes is not seen. The gap is the provider's and beneficiary's to choose.
- The page is judged as a status page. A health address that always answers 200 with a fixed "ok" is believed.
- The demo's three addresses are files committed to this repository.
