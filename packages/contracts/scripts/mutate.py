"""Mutation pass: break every defence on purpose, confirm a test notices.

Passing tests prove nothing on their own. Each entry below is a small edit to
the contract that removes a defence. The suite must fail for every one of them,
and this script records WHICH test caught it, so the table in the README is
measured rather than claimed.

    python scripts/mutate.py            # run them all, print what caught what
    python scripts/mutate.py --md       # emit the markdown table for the README

An escaping mutation is a finding, not a nuisance: either a missing test, or a
later defence strict enough that an earlier test can no longer fail. The script
exits non-zero if anything escapes, and refuses to run on a red baseline. A find
string that is missing, or matches more than once, is a failure of the harness,
never a skip, so refactoring cannot quietly turn a row off.
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).absolute().parent.parent
TARGET = "pulse.py"

FENCE = '    return str(raw).replace("<", "(").replace(">", ")").replace("[", "(").replace("]", ")")'

MUTATIONS = [
    # -- reading the status
    ("a 2xx status is not a 2xx", '    if 200 <= n < 300:\n        return "2xx"', '    if 200 < n < 300:\n        return "2xx"'),
    ("a 3xx status is a success", '    if 300 <= n < 400:\n        return "3xx"', '    if 300 <= n < 400:\n        return "2xx"'),
    ("a 4xx status is a 5xx", '    if 400 <= n < 500:\n        return "4xx"', '    if 400 <= n < 500:\n        return "5xx"'),
    ("a status that is not a number is read", "    except ValueError:\n        return \"none\"", "    except ValueError:\n        return \"2xx\""),

    # -- reading the answer
    ("an option past the list is accepted", "    if k < 0 or k >= n:\n        return \"\"", "    if k < 0:\n        return \"\""),
    ("an answer in words is read as a number",
     '    if s == "" or any(ch not in "0123456789" for ch in s) or len(s) > 2:', '    if s == "":'),

    # -- the two orders
    ("the second pass is asked in the forward order",
     "    rev, _ = ask(title, page, REVERSED)", "    rev, _ = ask(title, page, FORWARD)"),
    ("the reversed order is not reversed", "REVERSED = [FAILING, HEALTHY]", "REVERSED = [HEALTHY, FAILING]"),
    ("a disagreement between the orders is up",
     "    if forward != reverse:\n        return UNCLEAR", "    if forward != reverse:\n        return UP"),
    ("a disagreement between the orders is down",
     "    if forward != reverse:\n        return UNCLEAR", "    if forward != reverse:\n        return DOWN"),
    ("failing is read as up", "    return UP if forward == HEALTHY else DOWN", "    return UP if forward == FAILING else DOWN"),
    ("an answer is not read back through its order", "    return order[int(choice)]", "    return FORWARD[int(choice)]"),

    # -- reading the model
    ("an unusable answer is not retried",
     "    for _ in range(2):\n        raw = gl.nondet.exec_prompt(", "    for _ in range(1):\n        raw = gl.nondet.exec_prompt("),
    ("an unusable answer is read as healthy",
     '    raise gl.vm.UserError(f"{ERR_LLM} the model named neither option")', '    return HEALTHY, ""'),
    ("an answer that is not an object crashes the block",
     "        if isinstance(raw, dict):\n            choice", "        if True:\n            choice"),

    # -- the probe
    ("a failed fetch is not down", '    except Exception:                                  # noqa: BLE001\n        return DOWN, "none", "the address could not be fetched"',
     '    except Exception:                                  # noqa: BLE001\n        return UNCLEAR, "none", "the address could not be fetched"'),
    ("a status that is not 2xx is not down", '    if klass != "2xx":\n        return DOWN, klass,', '    if klass != "2xx":\n        return UNCLEAR, klass,'),
    ("a status that is not 2xx still asks the model", '    if klass != "2xx":\n        return DOWN, klass, "the address answered " + klass\n', ''),
    ("an empty page is read as up", '        return UNCLEAR, "2xx", "the page was empty"', '        return UP, "2xx", "the page was empty"'),
    ("an empty page is read as down", '        return UNCLEAR, "2xx", "the page was empty"', '        return DOWN, "2xx", "the page was empty"'),
    ("an empty page is still read by the model", "    if len(page.strip()) < MIN_PAGE:", "    if False:"),
    ("the address is never actually fetched", "        resp = gl.nondet.web.get(url)", "        resp = None"),

    # -- the validator
    ("the validator agrees with an error", "                return False\n            theirs", "                return True\n            theirs"),
    ("the validator skips the structural check",
     "            if not reading_sound(proposed[0], proposed[1]):\n                return False", "            if False:\n                return False"),
    ("the validator agrees with anything sound", '            return pulse_agrees((mine["state"], mine["class"]), proposed)', "            return True"),
    ("the validator agrees when its own fetch or model fails",
     "            except gl.vm.UserError:\n                return False", "            except gl.vm.UserError:\n                return True"),
    ("agreement ignores the class", "            and mine[0] == theirs[0] and mine[1] == theirs[1])", "            and mine[0] == theirs[0])"),
    ("agreement ignores the state", "            and mine[0] == theirs[0] and mine[1] == theirs[1])", "            and mine[1] == theirs[1])"),
    ("agreement ignores soundness",
     "    return (reading_sound(mine[0], mine[1]) and reading_sound(theirs[0], theirs[1])\n            and mine[0] == theirs[0] and mine[1] == theirs[1])",
     "    return mine[0] == theirs[0] and mine[1] == theirs[1]"),
    ("an unknown state is sound", "    if state not in STATES or klass not in CLASSES:\n        return False", "    if False:\n        return False"),
    ("an up reading may come from any class", "    if state == UP:\n        return klass == \"2xx\"", "    if state == UP:\n        return True"),
    ("an unclear reading may come from any class", "    if state == UNCLEAR:\n        return klass == \"2xx\"", "    if state == UNCLEAR:\n        return True"),

    # -- the count
    ("a down adds no strike", "    if state == DOWN:\n        return int(strikes) + 1", "    if state == DOWN:\n        return int(strikes)"),
    ("an up does not clear the strikes", "    if state == UP:\n        return 0", "    if state == UP:\n        return int(strikes)"),
    ("an unclear clears the strikes", "    return int(strikes)\n\n\ndef breached", "    return 0\n\n\ndef breached"),
    ("a breach needs one strike too many", "    return int(strikes) >= int(needed)", "    return int(strikes) > int(needed)"),
    ("one strike is a breach", "    return int(strikes) >= int(needed)", "    return int(strikes) >= 1"),
    ("the agreed reading is not checked again",
     "        if not reading_sound(state, klass):\n            raise", "        if False:\n            raise"),
    ("the strike count is not stored", "        b.strikes = u256(strikes)", "        pass"),
    ("the worst run is not tracked", "        if strikes > int(b.worst):\n            b.worst = u256(strikes)", "        pass"),
    ("the strikes after a probe are recorded wrongly", "strikes_after=u256(strikes)", "strikes_after=u256(0)"),
    ("the probe time is not recorded", "        b.last_probe_at = u256(now)", "        pass"),
    ("probes are not linked", "            self.probes[int(b.last_probe)].next = u256(pid)", "            pass"),
    ("the probe count is not raised", "        b.n_probes = u256(int(b.n_probes) + 1)", "        pass"),
    ("a leader's reason is stored as sent", "why=sanitise_reason(res.get(\"because\", \"\")),", "why=str(res.get(\"because\", \"\")),"),
    ("a leader's reason is stored uncapped", '    return " ".join("".join(out).split())[:limit]', '    return " ".join("".join(out).split())'),

    # -- the payment
    ("a breach pays the provider", "            self._send(b.beneficiary, int(b.stake))", "            self._send(b.provider, int(b.stake))"),
    ("a breach pays nobody", "            self._send(b.beneficiary, int(b.stake))", "            pass"),
    ("a breach pays less than the stake", "            self._send(b.beneficiary, int(b.stake))", "            self._send(b.beneficiary, int(b.stake) - 1)"),
    ("a breach does not mark the bond breached", "            b.status = BREACHED", "            pass"),
    ("a breach does not record when", "            b.settled_at = u256(now)\n            self._send(b.beneficiary", "            self._send(b.beneficiary"),

    # -- the free refusals
    ("a probe is taken on a bond that is not open",
     '        if str(b.status) != OPEN:\n            raise gl.vm.UserError(f"{ERR_EXPECTED} this bond is {b.status}; only an open one is probed")',
     '        if False:\n            raise gl.vm.UserError(f"{ERR_EXPECTED} this bond is {b.status}; only an open one is probed")'),
    ("probes never close", "        if now > int(b.deadline):\n            raise gl.vm.UserError(f\"{ERR_EXPECTED} the term ended", "        if False:\n            raise gl.vm.UserError(f\"{ERR_EXPECTED} the term ended"),
    ("a bond takes any number of probes", "        if int(b.n_probes) >= MAX_PROBES:", "        if False:"),
    ("a probe may come sooner than the gap", "        if too_soon(now, int(b.last_probe_at), int(b.gap), int(b.n_probes)):", "        if False:"),
    ("the gap is exclusive", "    return int(now) < int(last_probe_at) + int(gap)", "    return int(now) <= int(last_probe_at) + int(gap)"),
    ("the first probe is too soon", "    if int(n_probes) == 0:\n        return False", "    if False:\n        return False"),
    ("the gap is ignored after the first probe", "    return int(now) < int(last_probe_at) + int(gap)", "    return False"),

    # -- settle
    ("a bond settles while the term runs", "        if now <= int(b.deadline):\n            raise", "        if False:\n            raise"),
    ("a breached or kept bond settles again",
     '        if str(b.status) != OPEN:\n            raise gl.vm.UserError(f"{ERR_EXPECTED} this bond is {b.status}; nothing to settle")',
     '        if False:\n            raise gl.vm.UserError(f"{ERR_EXPECTED} this bond is {b.status}; nothing to settle")'),
    ("settle pays the beneficiary", "        self._send(b.provider, int(b.stake))\n\n    # -- reads", "        self._send(b.beneficiary, int(b.stake))\n\n    # -- reads"),
    ("settle returns nothing", "        self._send(b.provider, int(b.stake))\n\n    # -- reads", "        pass\n\n    # -- reads"),
    ("settle is not recorded", "        b.status = KEPT", "        pass"),

    # -- money
    ("a stake of nothing is accepted", "        if stake < 1 or stake > MAX_AMOUNT:", "        if stake > MAX_AMOUNT:"),
    ("the held counter is not raised", "        self.held = u256(int(self.held) + stake)", "        pass"),
    ("a payout beyond what is held is sent", "        if amount > int(self.held):", "        if False:"),
    ("the held counter is not lowered", "        self.held = u256(int(self.held) - amount)", "        pass"),

    # -- opening
    ("the provider may name itself as the beneficiary", "        if who == gl.message.sender_address:\n            raise", "        if False:\n            raise"),
    ("the beneficiary need not look like an address", "        if not looks_like_address(beneficiary):", "        if False:"),
    ("the address is not checked", "        if not bounded(link, MIN_URL, MAX_URL) or not is_http_url(link):", "        if False:"),
    ("an address with angle brackets is accepted", '    if rest == "" or any(ch in s for ch in " <>\\"\'`\\\\"):', '    if rest == "":'),
    ("the gap is unbounded", "        if g < MIN_GAP or g > MAX_GAP:", "        if False:"),
    ("the number of strikes is unbounded", "        if k < MIN_STRIKES or k > MAX_STRIKES:", "        if False:"),
    ("the term is unbounded", "        if w < MIN_TERM or w > MAX_TERM:", "        if False:"),
    ("the term does not set the clock", "deadline=u256(now + w)", "deadline=u256(now + MAX_TERM)"),
    ("the number of strikes is not stored", "gap=u256(g), needed=u256(k),", "gap=u256(g), needed=u256(2),"),
    ("the gap is not stored", "gap=u256(g), needed=u256(k),", "gap=u256(MIN_GAP), needed=u256(k),"),
    ("the title is unbounded", "        if not bounded(t, MIN_TITLE, MAX_TITLE):", "        if False:"),

    # -- the prompt boundary
    ("the fence is removed", FENCE, "    return str(raw)"),
    ("the fence leaves square brackets", FENCE, '    return str(raw).replace("<", "(").replace(">", ")")'),
    ("the fetched page reaches the prompt unfenced", "{fence(page[:MAX_PAGE_SHOWN])}", "{page[:MAX_PAGE_SHOWN]}"),
    ("the service name reaches the prompt unfenced", "{fence(title)}", "{title}"),
    ("a whole page, however long, reaches the prompt", "{fence(page[:MAX_PAGE_SHOWN])}", "{fence(page)}"),
    ("the prompt lets the model guess", "Judge only what\nthe page says; do not guess what it might mean.", "Guess what it might mean."),
    ("control characters are stored", '            out.append(" ")\n        else:', "            out.append(ch)\n        else:"),
]

PYTEST = [sys.executable, "-m", "pytest", "tests", "-x", "-q", "--no-header", "-p", "no:cacheprovider"]


def copy_repo(tmp):
    dst = pathlib.Path(tmp) / "pkg"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", ".git", "node_modules", "*.pyc"))
    return dst


def run_one(label, find, replace):
    with tempfile.TemporaryDirectory() as tmp:
        dst = copy_repo(tmp)
        target = dst / TARGET
        src = target.read_text(encoding="utf-8")
        hits = src.count(find)
        if hits == 0:
            return "PATTERN NOT FOUND", None
        if hits > 1:
            return "PATTERN NOT UNIQUE", None
        target.write_text(src.replace(find, replace, 1), encoding="utf-8", newline="\n")
        proc = subprocess.run(PYTEST, cwd=dst, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            return "ESCAPED", None
        text = proc.stdout + proc.stderr
        m = re.search(r"^(?:FAILED|ERROR) (\S+?)::(\S+?)(?:\[|\s|$)", text, re.M)
        if m:
            return "caught", m.group(2).split("::")[-1]
        m = re.search(r"^E\s+(\w*(?:Error|Exception))", text, re.M)
        if m:
            return "caught", m.group(1) + " at import"
        return "caught", "unnamed failure"


def baseline_is_green():
    with tempfile.TemporaryDirectory() as tmp:
        dst = copy_repo(tmp)
        proc = subprocess.run(PYTEST, cwd=dst, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true", help="emit the README table")
    args = ap.parse_args()

    green, tail = baseline_is_green()
    if not green:
        print("the unmutated suite is not green; every mutation would look caught:\n" + tail, file=sys.stderr)
        return 2

    rows, escaped = [], []
    for label, find, replace in MUTATIONS:
        status, test = run_one(label, find, replace)
        if status == "caught":
            rows.append((label, test))
            if not args.md:
                print("  caught   %-70s %s" % (label, test), flush=True)
        else:
            escaped.append((label, status))
            print("  %-8s %s" % (status, label), file=sys.stderr, flush=True)

    if args.md:
        print("| Mutation | Caught by |")
        print("|---|---|")
        for label, test in rows:
            print("| %s | `%s` |" % (label, test))
    else:
        print()
        print("  %d mutations, %d caught, %d escaped" % (len(MUTATIONS), len(rows), len(escaped)))
    return 1 if escaped else 0


if __name__ == "__main__":
    sys.exit(main())
