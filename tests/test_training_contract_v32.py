from locdex.routing.training.evaluator import calibration_bins
from locdex.routing.training.labels import success_label
from locdex.routing.training.train import training_contract
def test_verification_is_primary_training_label(): assert success_label(compile_passed=True,tests_passed=True,lint_passed=True,validator_passed=True,escalated=False,reverted=False) and not success_label(compile_passed=True,tests_passed=False,lint_passed=True,validator_passed=True,escalated=False,reverted=False)
def test_training_contract_is_offline(): assert training_contract()["online_training"] is False
def test_calibration_bins_compare_prediction_to_outcome(): assert calibration_bins([{"predicted_success":.91,"success":True},{"predicted_success":.92,"success":False}])[-1]["n"]==2
