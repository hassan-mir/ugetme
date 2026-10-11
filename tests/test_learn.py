import unittest

from ugetme.learn import replacements, similarity

BASE = "Ask nimbis to review the login change and then deploy it to staging today."


class LearnTest(unittest.TestCase):
    def test_similarity(self):
        self.assertEqual(similarity(BASE, BASE), 1.0)
        self.assertLess(similarity(BASE, "something completely different here"), 0.3)

    def test_name_swap_is_learned(self):
        self.assertEqual(replacements(BASE, BASE.replace("nimbis", "Nimbus")), [("nimbis", "Nimbus")])

    def test_case_only_fix_is_learned(self):
        self.assertEqual(replacements(BASE, BASE.replace("nimbis", "NIMBIS")), [("nimbis", "NIMBIS")])

    def test_multi_word_name(self):
        text = "Open cloud code and run the tests for the login page before lunch."
        self.assertEqual(replacements(text, text.replace("cloud code", "Claude Code")),
                         [("cloud code", "Claude Code")])

    def test_plain_word_swap_is_ignored(self):
        self.assertEqual(replacements(BASE, BASE.replace("today", "tomorrow")), [])

    def test_punctuation_is_stripped(self):
        text = "Please ping nimbis, then merge the branch into main after the review."
        self.assertEqual(replacements(text, text.replace("nimbis,", "Nimbus,")), [("nimbis", "Nimbus")])

    def test_markdown_around_names_is_ignored(self):
        text = "Just list the files in the `Nimbus` folder for me please, and nothing else."
        self.assertEqual(replacements(text, text.replace("`Nimbus`", "`NimbusHQ`")), [("Nimbus", "NimbusHQ")])
        text = "Please ask **nimbis** to review the login change before lunch today."
        self.assertEqual(replacements(text, text.replace("**nimbis**", "**Nimbus**")), [("nimbis", "Nimbus")])

    def test_content_edits_are_not_learned(self):
        text = "Use postgres for the cache and retry 5 times before you give up on the job."
        self.assertEqual(replacements(text, text.replace("postgres", "MySQL").replace("5", "3")), [])
        self.assertEqual(replacements(text, text.replace("retry 5", "retry 15")), [])  # sounds alike, but a number
        text = "It should read the file first and then write the result back to disk."
        self.assertEqual(replacements(text, text.replace("It", "This")), [])

    def test_sound_alike_fixes_are_learned(self):
        text = "Please open the andy settings page and check the new hotkey for dictation today."
        self.assertEqual(replacements(text, text.replace(" andy ", " Handy ")), [("andy", "Handy")])

    def test_rewrite_learns_nothing(self):
        self.assertIsNone(replacements(BASE, "Actually forget it, write a poem about cats."))

    def test_no_edit(self):
        self.assertEqual(replacements(BASE, BASE), [])

    def test_a_capital_after_a_sentence_end_inside_the_words_is_not_a_name(self):
        clean = "Ideally we can reuse the staging database and endpoints so that helps a lot today."
        sent = "Ideally we can reuse the staging database and points, right? So, yeah that helps a lot today."
        self.assertEqual(replacements(clean, sent), [])
