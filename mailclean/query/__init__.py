"""Query language parser and evaluator."""

from .lexer import Lexer, Token, TokenType
from .parser import Parser
from .criteria import (
    Criterion,
    FromCriterion,
    ToCriterion,
    CcCriterion,
    BccCriterion,
    AddresseeCriterion,
    DateCriterion,
    BeforeCriterion,
    AfterCriterion,
    OlderThanCriterion,
    NewerThanCriterion,
    SubjectCriterion,
    BodyCriterion,
    AndCriterion,
    OrCriterion,
    NotCriterion,
)
from .evaluator import evaluate_query

__all__ = [
    'Lexer',
    'Token',
    'TokenType',
    'Parser',
    'Criterion',
    'FromCriterion',
    'ToCriterion',
    'CcCriterion',
    'BccCriterion',
    'AddresseeCriterion',
    'DateCriterion',
    'BeforeCriterion',
    'AfterCriterion',
    'OlderThanCriterion',
    'NewerThanCriterion',
    'SubjectCriterion',
    'BodyCriterion',
    'AndCriterion',
    'OrCriterion',
    'NotCriterion',
    'evaluate_query',
]
