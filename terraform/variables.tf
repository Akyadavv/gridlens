variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket for raw landing files, e.g. gridlens-raw-<suffix>."
  type        = string
}

variable "force_destroy_bucket" {
  description = "Allow `terraform destroy` to delete a non-empty bucket (handy for a demo project)."
  type        = bool
  default     = false
}

variable "ingest_principal_role_name" {
  description = "Optional existing IAM role (e.g. the Airflow worker role) to attach the S3 writer policy to."
  type        = string
  default     = ""
}

variable "snowpipe_sqs_arn" {
  description = <<-EOT
    SQS ARN from the `notification_channel` column of SHOW PIPES. Leave empty on the first
    apply; create the pipes (snowflake/01b_s3_snowpipe.sql), then apply again with it set.
  EOT
  type        = string
  default     = ""
}

variable "snowflake_organization" {
  type = string
}

variable "snowflake_account" {
  type = string
}

variable "snowflake_admin_user" {
  type = string
}

variable "snowflake_admin_private_key_path" {
  type = string
}

variable "snowflake_service_user" {
  type    = string
  default = "GRIDLENS_SVC"
}

variable "snowflake_service_user_public_key" {
  description = "RSA public key body (no BEGIN/END lines) for the service user."
  type        = string
}

variable "reporter_users" {
  description = "Existing human Snowflake users who should get the REPORTER role."
  type        = list(string)
  default     = []
}

variable "monthly_credit_quota" {
  description = "Hard monthly credit cap for the gridlens warehouse."
  type        = number
  default     = 10
}

variable "resource_monitor_notify_users" {
  description = "Users (with verified emails) notified at resource-monitor thresholds."
  type        = list(string)
  default     = []
}
