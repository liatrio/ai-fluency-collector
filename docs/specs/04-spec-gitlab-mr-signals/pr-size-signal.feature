# Source: docs/specs/04-spec-gitlab-mr-signals/04-spec-gitlab-mr-signals.md
# Pattern: CLI/Process + Error Handling
# Recommended test type: Integration + Unit

Feature: PR Size Signal

  Scenario: Scan produces pr_size signal for team with AI-attributed MRs
    Given a team config with GitLab members who have merged AI-attributed MRs in the survey period
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output contains a source entry with "source_id" equal to "gitlab-mr"
    And that source contains a signal with "skill_id" equal to "im-supervised-agent"
    And the signal has a "score" between 10 and 100 inclusive
    And the evidence string matches the pattern "PR size (AI-attributed): \d+ median lines changed \(N=\d+ MRs\)"

  Scenario: pr_size signal is omitted when no AI-attributed MRs exist in the period
    Given a team config with GitLab members who have no AI-attributed MRs in the survey period
    And the GITLAB_TOKEN environment variable is set
    When the user runs "afc scan --config team.yaml"
    Then the JSON output does not contain a signal with "skill_id" equal to "im-supervised-agent" under "source_id" "gitlab-mr"

  Scenario: Median pr_size below 200 lines scores 100
    Given a set of AI-attributed MRs with changes_count values of [50, 80, 120]
    When the mr_scanner computes the pr_size signal
    Then the median is 80
    And the emitted score is 100

  Scenario: Median pr_size between 200 and 399 lines scores 80
    Given a set of AI-attributed MRs with changes_count values of [150, 250, 300]
    When the mr_scanner computes the pr_size signal
    Then the median is 250
    And the emitted score is 80

  Scenario: Median pr_size between 400 and 799 lines scores 60
    Given a set of AI-attributed MRs with changes_count values of [400, 600, 700]
    When the mr_scanner computes the pr_size signal
    Then the median is 600
    And the emitted score is 60

  Scenario: Median pr_size between 800 and 1499 lines scores 35
    Given a set of AI-attributed MRs with changes_count values of [800, 1000, 1400]
    When the mr_scanner computes the pr_size signal
    Then the median is 1000
    And the emitted score is 35

  Scenario: Median pr_size at or above 1500 lines scores 10
    Given a set of AI-attributed MRs with changes_count values of [1500, 2000, 3000]
    When the mr_scanner computes the pr_size signal
    Then the median is 2000
    And the emitted score is 10

  Scenario: MRs with changes_count of None are excluded from the median
    Given a set of AI-attributed MRs where one has changes_count of None and two have values of [100, 200]
    When the mr_scanner computes the pr_size signal
    Then the MR with None is excluded from the calculation
    And the median is computed from the two valid values only
    And the emitted score reflects the valid median

  Scenario: MRs with changes_count of "too many changes" are excluded from the median
    Given a set of AI-attributed MRs where one has changes_count of "too many changes" and two have values of [300, 500]
    When the mr_scanner computes the pr_size signal
    Then the MR with the string value is excluded from the calculation
    And the median is computed from the two numeric values only
    And the emitted score reflects the valid median

  Scenario: All AI-attributed MRs have unparseable changes_count and no signal is emitted
    Given a set of AI-attributed MRs where all have changes_count of "too many changes"
    When the mr_scanner computes the pr_size signal
    Then no pr_size signal is emitted for the period
