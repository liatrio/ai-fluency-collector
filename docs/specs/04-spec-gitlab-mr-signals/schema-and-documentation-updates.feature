# Source: docs/specs/04-spec-gitlab-mr-signals/04-spec-gitlab-mr-signals.md
# Pattern: CLI/Process
# Recommended test type: Integration

Feature: Schema and Documentation Updates

  Scenario: Output JSON accepts gitlab-mr as a valid source_id
    Given a team config with GitLab members who have AI-attributed MRs in the survey period
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output contains a top-level "sources" array
    And one entry in that array has "source_id" equal to "gitlab-mr"
    And the entry has a non-empty "signals" array

  Scenario: gitlab-mr source_id does not appear in output when no MR signals are collected
    Given a team config with GitLab members who have no AI-attributed MRs in the survey period
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output does not contain a source with "source_id" equal to "gitlab-mr"
    And the command exits with code 0

  Scenario: Scan completes without error when gitlab-mr scanner runs alongside existing scanners
    Given a valid team config with at least one configured project and one team member
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the command exits with code 0
    And the JSON output contains entries for all previously supported source_ids that have data
    And no source_id is duplicated in the output
