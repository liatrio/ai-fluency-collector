# Source: docs/specs/02-spec-missing-signals/02-spec-missing-signals.md
# Pattern: CLI/Process (scoring function called by afc scan); verification via JSON output field
# Recommended test type: Unit

Feature: missing_signals in calculate_member_scores()

  Scenario: missing_signals lists absent co-author pattern IDs when only some patterns were triggered
    Given a member skill mapping with two contributing co-author pattern IDs
    And member activity results where only one pattern ID was matched by at least one member
    When calculate_member_scores() is called with those results
    Then the emitted scoring_context for that skill contains a missing_signals list
    And the missing_signals list includes only the co-author pattern ID that had zero member matches

  Scenario: missing_signals is absent from scoring_context when all contributing patterns had member matches
    Given a member skill mapping with two contributing co-author pattern IDs
    And member activity results where both pattern IDs were matched by at least one member
    When calculate_member_scores() is called with those results
    Then the emitted scoring_context for that skill does not contain a missing_signals key

  Scenario: existing scoring_context fields are unchanged when missing_signals is added to member scores
    Given a member skill mapping with one contributing co-author pattern ID that had zero member matches
    When calculate_member_scores() is called with those results
    Then the emitted signal still contains the original breakdown, score, and evidence fields
    And those fields have the same values as before missing_signals was introduced
