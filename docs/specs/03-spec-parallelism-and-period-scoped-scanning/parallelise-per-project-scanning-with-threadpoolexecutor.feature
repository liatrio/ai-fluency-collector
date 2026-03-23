# Source: docs/specs/03-spec-parallelism-and-period-scoped-scanning/03-spec-parallelism-and-period-scoped-scanning.md
# Pattern: Async/Concurrent + CLI/Process
# Recommended test type: Integration

Feature: Parallelise Per-Project Scanning with ThreadPoolExecutor

  Scenario: All projects are scanned and results appear in project list order
    Given a team config with 3 projects: "group/alpha", "group/beta", "group/gamma"
    And the GitLab API returns distinct artifact results for each project
    When the user runs "afc scan --config team.yaml"
    Then the output JSON contains artifact signal entries for all 3 projects
    And the entries appear in the order "group/alpha", "group/beta", "group/gamma"
    And no project result is missing or duplicated

  Scenario: Scan completes successfully with multiple projects configured
    Given a team config with 5 projects and a valid GITLAB_TOKEN
    When the user runs "afc scan --config team.yaml --period 2026-W10"
    Then the command exits with code 0
    And an output JSON file is created containing results for all 5 projects
    And stderr contains no error messages

  Scenario: A GitLab API error on one project terminates the scan with an error
    Given a team config with 3 projects where "group/bad-project" returns a 403 Forbidden response
    When the user runs "afc scan --config team.yaml"
    Then the command exits with a non-zero exit code
    And stderr contains an error message referencing the failed project
    And no partial output file is written for that scan run

  Scenario: Parallel artifact scans do not mix results between projects
    Given a team config with 2 projects: "group/proj-a" has a ".mcp.json" file and "group/proj-b" does not
    And both GitLab APIs respond concurrently
    When the user runs "afc scan --config team.yaml"
    Then the output JSON shows the ".mcp.json" signal only under "group/proj-a"
    And the signal entry for "group/proj-b" does not include the ".mcp.json" artifact

  Scenario: Review scanner is not run in parallel and still produces correct results
    Given a team config with 2 projects and 1 survey week
    And the GitLab API returns MR review data for both projects
    When the user runs "afc scan --config team.yaml"
    Then the output JSON contains a "gitlab-review-signals" source with results from both projects
    And the command exits with code 0
