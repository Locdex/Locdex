def success_label(*,compile_passed,tests_passed,lint_passed,validator_passed,escalated,reverted):
    hard=[x for x in (compile_passed,tests_passed,lint_passed,validator_passed) if x is not None]
    return all(hard) and not reverted and not escalated
