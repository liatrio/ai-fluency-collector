# Source: docs/specs/03-spec-parallelism-and-period-scoped-scanning/03-spec-parallelism-and-period-scoped-scanning.md
# Pattern: CLI/Process + State
# Recommended test type: Integration

Feature: Period-Scoped Dates for Member Scanner and Active-Branch Cutoff

  Scenario: Member scanner fetches commits starting from the period start date
    Given a team config for survey period "2026-W01"
    And the GitLab API is stubbed to record the since_date passed to get_project_commits
    When the user runs "afc scan --config team.yaml --period 2026-W01"
    Then the since_date passed to get_project_commits equals "2025-12-29" (Monday of 2026-W01)
    And no commits earlier than "2025-12-29" are requested from the API

  Scenario: Active-branch cutoff uses period end date, not today
    Given a team config for survey period "2026-W01"
    And the GitLab API is stubbed to record the reference date passed to _get_active_branches
    When the user runs "afc scan --config team.yaml --period 2026-W01"
    Then the reference_date passed to _get_active_branches equals "2026-01-04" (Sunday of 2026-W01)
    And branches with last commit before "2025-10-06" (90 days before period end) are treated as inactive

  Scenario: Historical scan excludes branches that became active after the period ended
    Given a team config with one project containing a branch last committed on "2026-02-01"
    And the survey period is set to "2026-W01" (ending 2026-01-04)
    When the user runs "afc scan --config team.yaml --period 2026-W01"
    Then the branch committed on "2026-02-01" is not included in the artifact scan results
    And the output JSON contains results scoped to branches active within the 2026-W01 period

  Scenario: Member scanner uses period-start since_date instead of a today-relative lookback
    Given a team config for survey period "2025-W50"
    And today's date is "2026-03-23" (more than 90 days after the period)
    And the GitLab API is stubbed to record commit fetch parameters
    When the user runs "afc scan --config team.yaml --period 2025-W50"
    Then the since_date passed to get_project_commits equals "2025-12-08" (Monday of 2025-W50)
    And the since_date is not computed relative to today
