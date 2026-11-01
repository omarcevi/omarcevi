import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import update_readme as ur  # noqa: E402


class MarkdownEscape(unittest.TestCase):
    def test_escapes_characters_that_would_turn_into_formatting(self):
        self.assertEqual(ur.md_escape("CrewAI tools with **kwargs"), r"CrewAI tools with \*\*kwargs")
        self.assertEqual(ur.md_escape("a [link] and `code` and _x_ <b>"), r"a \[link\] and \`code\` and \_x\_ &lt;b>")

    def test_leaves_plain_text_alone(self):
        self.assertEqual(ur.md_escape("One H100, Many Models: What I Learned"), "One H100, Many Models: What I Learned")


class ReplaceSection(unittest.TestCase):
    PAGE = "intro\n<!-- WRITING:START -->\nold line\n<!-- WRITING:END -->\noutro\n"

    def test_replaces_only_the_lines_between_the_markers(self):
        out = ur.replace_section(self.PAGE, "WRITING", "- new post")
        self.assertEqual(out, "intro\n<!-- WRITING:START -->\n- new post\n<!-- WRITING:END -->\noutro\n")

    def test_replacing_twice_with_the_same_body_changes_nothing(self):
        once = ur.replace_section(self.PAGE, "WRITING", "- new post")
        self.assertEqual(ur.replace_section(once, "WRITING", "- new post"), once)

    def test_missing_markers_raise(self):
        with self.assertRaises(ur.UpdateError):
            ur.replace_section("no markers here", "WRITING", "- new post")


EVENTS_MD = """# Events

Notes about the format. One block per event:

- `type`: talk or workshop (required)

## Retrieval Is All You Need (Almost)
- type: talk
- event: DevFest İzmir 2026
- date: 2026-12-05
- link: https://example.com/devfest-izmir

## Building Trabzonspor's AI Analysis Room
- type: workshop
- event: DevFest Trabzon 2026
- date: 2026-10-31
- link: https://example.com/devfest-trabzon
- guide: /workshops/match-day-agents/
- repo: https://github.com/omarcevi/trabzonspor_analyst

## Something this month
- type: talk
- date: 2026-11

## Managing Agentic Systems on Google Cloud
- type: talk
- event: Google Developer Day Istanbul
- date: 2026-09-20
- video: https://youtube.com/watch?v=abc
- link: https://example.com/gdd

## Beyond ML *Notebook*
- type: talk
- date: 2023-03

## But What Is TensorFlow?
- type: talk
- date: 2022
"""


class ParseEvents(unittest.TestCase):
    def test_reads_each_block_and_skips_the_notes_above_the_first_one(self):
        events = ur.parse_events(EVENTS_MD)
        self.assertEqual(len(events), 6)
        self.assertEqual(events[1]["title"], "Building Trabzonspor's AI Analysis Room")
        self.assertEqual(events[1]["guide"], "/workshops/match-day-agents/")
        self.assertEqual(events[1]["type"], "workshop")


class RenderSpeaking(unittest.TestCase):
    TODAY = ur.datetime.date(2026, 11, 2)

    def render(self, text=EVENTS_MD, today=TODAY):
        return ur.render_speaking(ur.parse_events(text), today)

    def test_next_is_the_soonest_full_dated_event_from_today_on(self):
        first = self.render().splitlines()[0]
        self.assertEqual(
            first,
            "**Next:** [Retrieval Is All You Need (Almost)](https://example.com/devfest-izmir)"
            " · DevFest İzmir 2026 · 5 December 2026",
        )

    def test_lists_the_three_most_recent_past_events_newest_first(self):
        items = [line for line in self.render().splitlines() if line.startswith("- ")]
        self.assertEqual(items, [
            "- [Building Trabzonspor's AI Analysis Room](https://omarcevi.dev/workshops/match-day-agents/)"
            " · DevFest Trabzon 2026 · workshop",
            "- [Managing Agentic Systems on Google Cloud](https://youtube.com/watch?v=abc) · Google Developer Day Istanbul",
            r"- Beyond ML \*Notebook\* · Mar 2023",
        ])

    def test_an_event_dated_only_with_the_current_month_is_left_out(self):
        self.assertNotIn("Something this month", self.render())

    def test_without_an_upcoming_event_there_is_no_next_line(self):
        out = self.render(today=ur.datetime.date(2027, 1, 1))
        self.assertNotIn("**Next:**", out)
        self.assertTrue(out.startswith("- [Retrieval Is All You Need (Almost)]"))

    def test_ends_with_a_link_to_the_full_list(self):
        self.assertEqual(self.render().splitlines()[-1], "[All talks and workshops →](https://omarcevi.dev/#speaking)")


MEDIUM_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title><![CDATA[Stories by Omar Elcircevi on Medium]]></title>
<link>https://medium.com/@omarcevi?source=rss-afee45315b65------2</link>
<item><title><![CDATA[I Stopped Chasing the GDE Title. That's When I Got It.]]></title>
<link>https://omarcevi.medium.com/gde-eb385130109e?source=rss-afee45315b65------2</link>
<pubDate>Mon, 07 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title><![CDATA[One Framework to Deploy Them All! Meet NVIDIA Triton]]></title>
<link>https://levelup.gitconnected.com/triton-6a3887b0dd2b?source=rss-afee45315b65------2</link>
<pubDate>Tue, 13 Oct 2026 09:00:00 GMT</pubDate></item>
<item><title><![CDATA[One H100, Many Models]]></title>
<link>https://omarcevi.medium.com/one-h100-9eb635db2311?source=rss-afee45315b65------2</link>
<pubDate>Mon, 21 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title><![CDATA[Revisiting Basics: Software Design Principles]]></title>
<link>https://omarcevi.medium.com/basics-1?source=rss</link>
<pubDate>Fri, 01 Aug 2025 09:00:00 GMT</pubDate></item>
</channel></rss>"""


class Writing(unittest.TestCase):
    def test_lists_the_three_newest_posts_with_clean_links(self):
        out = ur.render_writing(ur.parse_medium(MEDIUM_RSS))
        self.assertEqual(out.splitlines(), [
            "- [One Framework to Deploy Them All! Meet NVIDIA Triton](https://levelup.gitconnected.com/triton-6a3887b0dd2b) · Oct 2026",
            "- [One H100, Many Models](https://omarcevi.medium.com/one-h100-9eb635db2311) · Sep 2026",
            "- [I Stopped Chasing the GDE Title. That's When I Got It.](https://omarcevi.medium.com/gde-eb385130109e) · Sep 2026",
        ])

    def test_a_feed_with_no_posts_is_an_error(self):
        empty = b"<rss><channel><title>x</title></channel></rss>"
        with self.assertRaises(ur.UpdateError):
            ur.render_writing(ur.parse_medium(empty))


SEARCH_ITEM = {
    "repository_url": "https://api.github.com/repos/google/adk-web",
    "number": 272,
    "title": "Feat: Add light and dark theme toggle support to ADK Web UI",
    "html_url": "https://github.com/google/adk-web/pull/272",
    "pull_request": {"merged_at": "2025-11-14T04:24:43Z"},
}
PULL = {
    "base": {"repo": {"full_name": "google/adk-python"}},
    "number": 3037,
    "title": "fix: #3036 parameter filtering for CrewAI functions with **kwargs",
    "html_url": "https://github.com/google/adk-python/pull/3037",
    "merged_at": None,
    "closed_at": "2025-10-01T10:00:00Z",
}


class OpenSource(unittest.TestCase):
    def test_clean_title_drops_commit_prefixes_and_leading_issue_numbers(self):
        self.assertEqual(ur.clean_pr_title("Feat: Add light and dark theme"), "Add light and dark theme")
        self.assertEqual(ur.clean_pr_title("fix: #3036 parameter filtering"), "Parameter filtering")
        self.assertEqual(ur.clean_pr_title("feat(ui)!: dark mode"), "Dark mode")
        self.assertEqual(ur.clean_pr_title("Add a sample agent"), "Add a sample agent")

    def test_extra_list_reads_urls_and_optional_titles_and_skips_comments(self):
        text = "# notes\n\nhttps://github.com/google/adk-python/pull/3037 | Fix CrewAI tools\nhttps://github.com/a/b/pull/1\n"
        self.assertEqual(ur.parse_extra(text), [
            ("https://github.com/google/adk-python/pull/3037", "Fix CrewAI tools"),
            ("https://github.com/a/b/pull/1", None),
        ])

    def test_a_pull_from_search_and_a_hand_listed_pull_end_up_alike(self):
        self.assertEqual(ur.pr_from_search(SEARCH_ITEM), {
            "repo": "google/adk-web", "title": "Add light and dark theme toggle support to ADK Web UI",
            "url": "https://github.com/google/adk-web/pull/272", "date": "2025-11-14T04:24:43Z",
        })
        self.assertEqual(ur.pr_from_pull(PULL, "Fix CrewAI tools that take **kwargs"), {
            "repo": "google/adk-python", "title": "Fix CrewAI tools that take **kwargs",
            "url": "https://github.com/google/adk-python/pull/3037", "date": "2025-10-01T10:00:00Z",
        })

    def test_render_lists_newest_first_once_each_with_escaped_titles(self):
        a = ur.pr_from_search(SEARCH_ITEM)
        b = ur.pr_from_pull(PULL, "Fix CrewAI tools that take **kwargs")
        self.assertEqual(ur.render_contributions([b, a, a]).splitlines(), [
            "- **google/adk-web** · [Add light and dark theme toggle support to ADK Web UI](https://github.com/google/adk-web/pull/272)",
            r"- **google/adk-python** · [Fix CrewAI tools that take \*\*kwargs](https://github.com/google/adk-python/pull/3037)",
        ])

    def test_render_with_nothing_found_is_an_error(self):
        with self.assertRaises(ur.UpdateError):
            ur.render_contributions([])


class Update(unittest.TestCase):
    PAGE = ("<!-- SPEAKING:START -->\nold talks\n<!-- SPEAKING:END -->\n"
            "<!-- WRITING:START -->\nold posts\n<!-- WRITING:END -->\n")

    def test_a_failing_source_keeps_its_old_section_and_the_others_still_update(self):
        def broken():
            raise OSError("Medium is down")

        page, errors = ur.update(self.PAGE, {"SPEAKING": lambda: "new talks", "WRITING": broken})
        self.assertIn("new talks", page)
        self.assertIn("old posts", page)
        self.assertEqual(len(errors), 1)
        self.assertIn("WRITING", errors[0])
        self.assertIn("Medium is down", errors[0])


if __name__ == "__main__":
    unittest.main()
