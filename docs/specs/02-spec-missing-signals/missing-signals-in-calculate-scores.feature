# Source: docs/specs/02-spec-missing-signals/02-spec-missing-signals.md
# Pattern: CLI/Process (scoring function called by afc scan); verification via JSON output field
# Recommended test type: Unit

Feature: missing_signals in calculate_scores() (GitLab artifacts and CI patterns)

  Scenario: missing_signals lists absent artifact IDs when only some contributing artifacts are found
    Given a skill mapping with two contributing artifact IDs
    And artifact scan results where only one of those artifact IDs was found across all projects
    When calculate_scores() is called with those results
    Then the emitted scoring_context for that skill contains a missing_signals list
    And the missing_signals list includes only the artifact ID that was not found

  Scenario: missing_signals is absent from scoring_context when all contributing artifact IDs were found
    Given a skill mapping with two contributing artifact IDs
    And artifact scan results where both artifact IDs were found in at least one project
    When calculate_scores() is called with those results
    Then the emitted scoring_context for that skill does not contain a missing_signals key

  Scenario: missing_signals lists absent CI pattern IDs when a CI skill has a missing pattern
    Given a CI skill mapping with one or more contributing CI pattern IDs
    And CI scan results where at least one of those pattern IDs was not matched in any project
    When calculate_scores() is called with those CI results
    Then the emitted scoring_context for that CI skill contains a missing_signals list
    And the missing_signals list includes the unmatched CI pattern ID

  Scenario: existing scoring_context fields are unchanged when missing_signals is added
    Given a skill mapping with one contributing artifact ID that is absent from scan results
    When calculate_scores() is called with those results
    Then the emitted signal still contains the original breakdown, score, and evidence fields
    And those fields have the same values as before missing_signals was introduced

  Scenario: duplicate artifact IDs in the skill mapping appear at most once in missing_signals
    Given a skill mapping where the same artifact ID appears in multiple mapping entries
    And artifact scan results where that artifact ID was not found
    When calculate_scores() is called with those results
    Then the missing_signals list contains that artifact ID exactly once
