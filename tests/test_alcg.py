import unittest
from pathlib import Path

from alcg import Call, Name, ParseError, String, audit, parse, read_expressions, render, to_data


ROOT = Path(__file__).resolve().parents[1]


class SyntaxTests(unittest.TestCase):
    def test_nested_round_trip(self):
        source = 'WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))'
        self.assertEqual(parse(render(parse(source))), parse(source))

    def test_unicode_and_escape_in_string(self):
        expression = parse(r'RAW(text="研究\nAI said: \"hello\"")')
        self.assertEqual(parse(render(expression)), expression)
        self.assertIsInstance(expression, Call)
        self.assertIsInstance(expression.args[0][1], String)

    def test_single_name(self):
        self.assertEqual(parse('WATER'), Name('WATER'))

    def test_empty_call(self):
        self.assertEqual(parse('PING()'), Call('PING', ()))

    def test_duplicate_argument_rejected(self):
        with self.assertRaises(ParseError):
            parse('IS(subject=WATER, subject=EARTH)')

    def test_ambiguous_and_invalid_syntax_rejected(self):
        for example in ['DO(actor=AI,)', 'X(ABC)', 'X(a=Y) remainder', 'X(a=2)', '']:
            with self.subTest(example=example), self.assertRaises(ParseError):
                parse(example)

    def test_ast_type(self):
        self.assertEqual(to_data(parse('A(x=B)'))['args']['x']['type'], 'name')

    def test_seed_file_and_audit(self):
        expressions = read_expressions(ROOT / 'samples/seed.alcg')
        self.assertEqual(len(expressions), 13)
        vocab = {line.strip() for line in (ROOT / 'data/seed-vocabulary.txt').read_text().splitlines()
                 if line.strip() and not line.startswith('#')}
        report = audit(expressions, vocab)
        self.assertEqual(report['RAW_nodes'], 1)
        self.assertEqual(report['structured_without_RAW'], 12)
        self.assertEqual(report['names_not_in_seed'], ['GREATER_THAN'])


if __name__ == '__main__':
    unittest.main()
