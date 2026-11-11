"""Cloud CLIs: a read (describe, list, get, show, ls...) is free; anything else leaves the machine and is high stakes,
including verbs written with dashes (terminate-instances, send-email, put-object)."""
import pytest

from tenure import classify

HIGH = ["aws ec2 terminate-instances --instance-ids i-1", "aws ses send-email --to a@b.c", "aws s3api put-object --body secrets.txt --bucket b --key k",
        "aws rds delete-db-instance --db-instance-identifier d", "aws iam attach-user-policy --user-name u --policy-arn p",
        "az storage blob upload -f a -c c", "az webapp up", "gcloud sql instances patch db --tier x",
        "aws s3 cp a s3://b", "gcloud compute instances create vm", "aws lambda invoke --function-name f out.json"]
FREE = ["aws s3 ls", "aws sts get-caller-identity", "aws ec2 describe-instances", "gcloud config list",
        "az account show", "gcloud compute instances list", "aws --profile p s3 ls"]


@pytest.mark.parametrize("cmd", HIGH)
def test_cloud_writes_are_high(cmd):
    assert classify.classify("terminal", {"command": cmd}, cwd="/p", home="/h").stakes == "high"


@pytest.mark.parametrize("cmd", FREE)
def test_cloud_reads_are_free(cmd):
    assert classify.classify("terminal", {"command": cmd}, cwd="/p", home="/h").stakes == "free"
