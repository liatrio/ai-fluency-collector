# Task 3.0 Proof Artifacts — GitLab CI Config Scanner

## Test Results

### `pytest tests/test_ci_scanner.py -v`
```
tests/test_ci_scanner.py::test_no_ci_file_returns_all_false PASSED
tests/test_ci_scanner.py::test_sast_via_template_include PASSED
tests/test_ci_scanner.py::test_sast_via_job_name PASSED
tests/test_ci_scanner.py::test_dast_via_include_string PASSED
tests/test_ci_scanner.py::test_secret_detection_via_template PASSED
tests/test_ci_scanner.py::test_secret_detection_via_job_name PASSED
tests/test_ci_scanner.py::test_ai_code_review PASSED
tests/test_ci_scanner.py::test_ai_test_generation PASSED
tests/test_ci_scanner.py::test_dependency_scanning_via_template PASSED
tests/test_ci_scanner.py::test_code_coverage_via_coverage_key PASSED
tests/test_ci_scanner.py::test_code_coverage_via_report PASSED
tests/test_ci_scanner.py::test_deployment_gates PASSED
tests/test_ci_scanner.py::test_multiple_patterns_in_one_file PASSED
tests/test_ci_scanner.py::test_include_list_of_strings PASSED
tests/test_ci_scanner.py::test_invalid_yaml_returns_all_false PASSED

15 passed
```

## CI Pattern Coverage

All 7 CI pattern types tested:
1. **SAST/DAST** — via template include and job name
2. **Secret detection** — via template include and job name
3. **AI code review** — via script content (`gitlab-duo review`)
4. **AI test generation** — via job name
5. **Dependency scanning** — via template include
6. **Code coverage** — via `coverage` key and `artifacts.reports.coverage_report`
7. **Deployment gates** — via deploy stage + environment + rules

## Include Directive Formats Tested
- String shorthand: `include: "Security/DAST.gitlab-ci.yml"`
- Template dict: `include: [{template: "Security/SAST.gitlab-ci.yml"}]`
- List of template dicts

## Edge Cases
- Missing `.gitlab-ci.yml` → all patterns False, no error
- Invalid YAML content → all patterns False, no error
- Multiple patterns in a single file → all detected

## Full Test Suite
```
46 passed in 0.25s
```

## Lint/Format
```
ruff check . → All checks passed!
ruff format --check . → All already formatted
```
