# Source: docs/specs/03-spec-parallelism-and-period-scoped-scanning/03-spec-parallelism-and-period-scoped-scanning.md
# Pattern: Async/Concurrent + CLI/Process
# Recommended test type: Integration

Feature: Parallelise Member Scanning and Cap get_jobs() Pagination

  Scenario: All members are scanned and results appear in member list order
    Given a team config with 3 members: "alice", "bob", "carol"
    And the GitLab API returns distinct commit co-author data for each member
    When the user runs "afc scan --config team.yaml"
    Then the output JSON contains "gitlab-member-activity" signal entries for all 3 members
    And the entries appear in the order "alice", "bob", "carol"
    And no member result is missing or duplicated

  Scenario: Concurrent member scans do not mix co-author results between members
    Given a team config with 2 members: "dev-a" has AI co-authored commits and "dev-b" does not
    And both GitLab user APIs respond concurrently
    When the user runs "afc scan --config team.yaml"
    Then the output JSON shows AI co-author signals only under "dev-a"
    And the signal entry for "dev-b" does not include AI co-author evidence

  Scenario: A GitLabUserNotFoundError for one member terminates the scan with an error
    Given a team config with 2 members where "unknown-user" does not exist in GitLab
    When the user runs "afc scan --config team.yaml"
    Then the command exits with a non-zero exit code
    And stderr contains an error message referencing "unknown-user"

  Scenario: get_jobs() stops fetching after 5 pages when more pages exist
    Given a GitLab project with 700 pipeline jobs spread across 7 pages
    And the GitLab API is instrumented to count page requests for get_jobs
    When the user runs "afc scan --config team.yaml"
    Then the number of page requests made to get_jobs does not exceed 5
    And the scan completes successfully with the jobs from the first 5 pages included in scoring

  Scenario: get_jobs() returns all jobs when fewer than 5 pages exist
    Given a GitLab project with 250 pipeline jobs spread across 3 pages
    When the user runs "afc scan --config team.yaml"
    Then all 250 jobs are included in the CI scan scoring
    And the command exits with code 0
