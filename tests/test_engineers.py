"""Engineers: the list, how names are understood, and 'take me to ...'."""

import json
import unittest
from pathlib import Path

from navigation.engineers import EngineerBook, distance
from tests import test_neutron


class Book(unittest.TestCase):
    book = EngineerBook()

    def test_all_38_are_there_once(self):
        names = [e.name for e in self.book.engineers]
        self.assertEqual(len(names), 38)
        self.assertEqual(len(set(names)), 38)

    def test_every_engineer_can_be_called_by_each_word_of_the_name(self):
        for e in self.book.engineers:
            self.assertIs(self.book.find(e.name), e, e.name)
            self.assertIs(self.book.find(e.spoken()), e, e.spoken())
            for word in e.words():
                if word in ("the", "colonel", "professor") or len(word) < 3:
                    continue
                self.assertIs(self.book.find(word), e, "%s / %s" % (e.name, word))

    def test_nicknames_titles_and_mishearings(self):
        for text, name in [("felicity", "Felicity Farseer"), ("farseer", "Felicity Farseer"), ("the dweller", "The Dweller"),
                           ("sarge", "The Sarge"), ("dekker", "Colonel Bris Dekker"), ("colonel dekker", "Colonel Bris Dekker"),
                           ("tod mcquinn", "Tod 'The Blaster' McQuinn"), ("palin", "Professor Palin"),
                           ("elvira martuk", "Elvira Martuuk"), ("engineer lori jameson", "Lori Jameson"), ("Baltanos", "Baltanos")]:
            self.assertEqual(self.book.find(text).name, name, text)

    def test_not_an_engineer(self):
        for text in ("sol", "my carrier", "the squad carrier", "colonia", "", "a", "the nearest station"):
            self.assertIsNone(self.book.find(text), text)

    def test_coordinates_are_sane(self):
        sol = self.book.find("dekker")
        self.assertEqual(sol.pos, (0, 0, 0))
        self.assertGreater(distance(sol.pos, self.book.find("petra").pos), 20000)       # Colonia
        self.assertIsNone(distance(None, sol.pos))


class Go(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setup_voice(self, system="Sol", pos=(0, 0, 0), **values):
        v = self.build(system=system, **values)
        self.state.star_pos = pos
        self.macro = []
        v.plot_macro = lambda s: self.macro.append(s) or (True, "")
        return v

    def test_close_engineer_uses_the_galaxy_map(self):
        v = self.setup_voice()
        for text in ("take me to Felicity Farseer", "Starling, take me to Farseer", "take us to Felicity", "go to felicity farseer",
                     "navigate to engineer felicity farseer", "plot a course to felicity"):
            self.macro.clear()
            self.build(system="Sol")
            v = self.setup_voice()
            self.assertIsNotNone(v.try_handle(text), text)
            self.assertEqual(self.macro, ["Deciat"], text)
            self.assertEqual(self.keys(), ["EngineerNear"], text)
            self.assertEqual(self.spansh.asked, [], text)

    def test_far_engineer_asks_spansh_for_a_neutron_route(self):
        v = self.setup_voice()
        v.try_handle("take me to Petra Olmanova")                       # Colonia, 22,000 ly away
        self.assertEqual(self.macro, [])
        self.assertIn(("find", "Asura"), self.spansh.asked)
        self.assertEqual(self.keys()[0], "EngineerFar")
        self.assertIn("route", [c[0] for c in self.spansh.asked])

    def test_exactly_the_limit_is_still_close(self):
        v = self.setup_voice(engineers__neutron_over_ly=50)
        v.try_handle("take me to Felicity Farseer")                    # Deciat is about 131 ly from Sol
        self.assertEqual(self.macro, [])
        self.assertIn(("find", "Deciat"), self.spansh.asked)
        v = self.setup_voice(engineers__neutron_over_ly=500)
        v.try_handle("take me to Felicity Farseer")
        self.assertEqual(self.macro, ["Deciat"])

    def test_unknown_position_uses_spansh(self):
        v = self.setup_voice(pos=None)
        v.try_handle("take me to Lori Jameson")
        self.assertEqual(self.keys()[0], "EngineerFarUnknown")
        self.assertIn(("find", "Shinrarta Dezhra"), self.spansh.asked)

    def test_already_there(self):
        v = self.setup_voice(system="Deciat", pos=(122.625, -0.8125, -47.28125))
        v.try_handle("take me to Felicity Farseer")
        self.assertEqual(self.keys(), ["EngineerHere"])
        self.assertEqual(self.macro, [])

    def test_where_is(self):
        v = self.setup_voice()
        v.try_handle("where is Felicity Farseer")
        self.assertEqual(self.keys(), ["EngineerWhere"])
        fields = self.narr.said[0][1]
        self.assertEqual((fields["system"], fields["station"]), ("Deciat", "Farseer Inc"))
        self.assertEqual(fields["distance"], "131")

    def test_macro_refused_is_explained(self):
        v = self.setup_voice()
        v.plot_macro = lambda s: (False, "this is not a safe moment to open the galaxy map")
        v.try_handle("take me to Felicity Farseer")
        self.assertEqual(self.keys(), ["EngineerPlotOff"])
        self.assertIn("safe moment", self.narr.said[0][1]["reason"])

    def test_other_commands_are_left_alone(self):
        v = self.setup_voice()
        for text in ("take me to the carrier", "where is the nearest station", "take us out", "go to sol", "plot a neutron route to colonia"):
            self.narr.said.clear()
            v.try_handle(text)
            self.assertNotIn("EngineerNear", self.keys(), text)
            self.assertNotIn("EngineerFar", self.keys(), text)
        self.assertEqual(self.macro, [])


class Lines(unittest.TestCase):
    def test_lines(self):
        data = json.loads(Path("voicepacks/default/engineers.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key in ("EngineerNear", "EngineerFar", "EngineerFarUnknown", "EngineerHere", "EngineerWhere", "EngineerPlotOff"):
            self.assertIn(key, data)
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertFalse([b for b in banned if b in line.lower()], line)
