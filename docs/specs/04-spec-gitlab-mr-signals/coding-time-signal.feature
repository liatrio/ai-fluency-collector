# Source: docs/specs/04-spec-gitlab-mr-signals/04-spec-gitlab-mr-signals.md
# Pattern: CLI/Process + Error Handling
# Recommended test type: Integration + Unit

Feature: Coding Time Signal

  Scenario: Scan produces coding_time signals for both skills when AI-attributed MRs exist
    Given a team config with GitLab members who have merged AI-attributed MRs in the survey period
    And each AI-attributed MR has at least one commit
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output contains a source entry with "source_id" equal to "gitlab-mr"
    And that source contains a signal with "skill_id" equal to "im-inline-editing"
    And that source contains a signal with "skill_id" equal to "im-supervised-agent"
    And the evidence strings match the pattern "Coding time (AI-attributed): \d+(\.\d+)?h median first commit to MR open \(N=\d+ MRs\)"

  Scenario: coding_time signal is omitted when no AI-attributed MRs exist in the period
    Given a team config with GitLab members who have no AI-attributed MRs in the survey period
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output does not contain signals with "skill_id" "im-inline-editing" or "im-supervised-agent" under "source_id" "gitlab-mr"

  Scenario: Median coding time under 2 hours scores 100
    Given AI-attributed MRs where the earliest commit to MR open times are [0.5, 1.0, 1.5] hours
    When the mr_scanner computes the coding_time signal
    Then the median is 1.0 hours
    And both the im-inline-editing and im-supervised-agent signals emit a score of 100

  Scenario: Median coding time between 2 and 7 hours scores 85
    Given AI-attributed MRs where the earliest commit to MR open times are [2.0, 4.0, 6.0] hours
    When the mr_scanner computes the coding_time signal
    Then the median is 4.0 hours
    And both the im-inline-editing and im-supervised-agent signals emit a score of 85

  Scenario: Median coding time between 8 and 23 hours scores 65
    Given AI-attributed MRs where the earliest commit to MR open times are [8.0, 12.0, 20.0] hours
    When the mr_scanner computes the coding_time signal
    Then the median is 12.0 hours
    And both the im-inline-editing and im-supervised-agent signals emit a score of 65

  Scenario: Median coding time between 24 and 71 hours scores 40
    Given AI-attributed MRs where the earliest commit to MR open times are [24.0, 48.0, 70.0] hours
    When the mr_scanner computes the coding_time signal
    Then the median is 48.0 hours
    And both the im-inline-editing and im-supervised-agent signals emit a score of 40

  Scenario: Median coding time at or above 72 hours scores 15
    Given AI-attributed MRs where the earliest commit to MR open times are [72.0, 100.0, 168.0] hours
    When the mr_scanner computes the coding_time signal
    Then the median is 100.0 hours
    And both the im-inline-editing and im-supervised-agent signals emit a score of 15

  Scenario: MRs with no commits are excluded from the coding time calculation
    Given a set of AI-attributed MRs where one has an empty commits list and two have commits
    And the two MRs with commits have coding times of [3.0, 5.0] hours
    When the mr_scanner computes the coding_time signal
    Then the MR with no commits is excluded from the calculation
    And the median is computed from the two valid MRs only
    And both signals emit a score of 85

  Scenario: All AI-attributed MRs have no commits and no signal is emitted
    Given a set of AI-attributed MRs where every MR has an empty commits list
    When the mr_scanner computes the coding_time signal
    Then no coding_time signal is emitted for the period

  Scenario: Coding time is derived from earliest commit timestamp not MR created_at
    Given an AI-attributed MR with two commits: one at T-10h and one at T-5h before MR open
    When the mr_scanner computes the coding time for that MR
    Then the coding time is 10 hours
    And it is not 5 hours
