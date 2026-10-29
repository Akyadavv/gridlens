output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "snowflake_s3_role_arn" {
  value = aws_iam_role.snowflake.arn
}

output "storage_integration" {
  value = snowflake_storage_integration.s3.name
}

output "ingest_write_policy_arn" {
  description = "Attach to whatever principal runs ingestion (Airflow worker role, CI user...)."
  value       = aws_iam_policy.ingest_write.arn
}

output "warehouse" {
  value = snowflake_warehouse.gridlens.name
}

output "next_step" {
  value = var.snowpipe_sqs_arn == "" ? "Run snowflake/01b_s3_snowpipe.sql, copy notification_channel from SHOW PIPES into snowpipe_sqs_arn, and apply again." : "Snowpipe auto-ingest notifications are wired up."
}
