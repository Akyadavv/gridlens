data "aws_caller_identity" "current" {}

locals {
  snowflake_role_name = "gridlens-snowflake-s3-read"
  # Built from the name (not the resource) to break the cycle: the storage integration
  # needs the role ARN, and the role's trust policy needs the integration's outputs.
  snowflake_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.snowflake_role_name}"
}

# ---- Raw landing bucket ------------------------------------------------------------------

resource "aws_s3_bucket" "raw" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy_bucket
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Raw files are already loaded into Snowflake within minutes; keep them cheap afterwards.
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "tier-down-raw"
    status = "Enabled"
    filter {
      prefix = ""
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 180
      storage_class = "GLACIER_IR"
    }
  }
}

# Snowpipe auto-ingest. All pipes in a Snowflake account/region share one SQS queue,
# so one notification covers every dataset prefix.
resource "aws_s3_bucket_notification" "snowpipe" {
  count  = var.snowpipe_sqs_arn == "" ? 0 : 1
  bucket = aws_s3_bucket.raw.id

  queue {
    queue_arn     = var.snowpipe_sqs_arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = ".ndjson.gz"
  }
}

# ---- IAM: Snowflake reads the bucket -----------------------------------------------------

data "aws_iam_policy_document" "snowflake_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [snowflake_storage_integration.s3.storage_aws_iam_user_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [snowflake_storage_integration.s3.storage_aws_external_id]
    }
  }
}

resource "aws_iam_role" "snowflake" {
  name               = local.snowflake_role_name
  assume_role_policy = data.aws_iam_policy_document.snowflake_trust.json
}

data "aws_iam_policy_document" "snowflake_read" {
  statement {
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.raw.arn]
  }
}

resource "aws_iam_role_policy" "snowflake_read" {
  name   = "s3-read-raw"
  role   = aws_iam_role.snowflake.id
  policy = data.aws_iam_policy_document.snowflake_read.json
}

# ---- IAM: ingestion writes the bucket ----------------------------------------------------

data "aws_iam_policy_document" "ingest_write" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn]
  }
}

resource "aws_iam_policy" "ingest_write" {
  name   = "gridlens-ingest-write"
  policy = data.aws_iam_policy_document.ingest_write.json
}

resource "aws_iam_role_policy_attachment" "ingest_write" {
  count      = var.ingest_principal_role_name == "" ? 0 : 1
  role       = var.ingest_principal_role_name
  policy_arn = aws_iam_policy.ingest_write.arn
}
