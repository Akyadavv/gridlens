locals {
  roles = {
    LOADER      = "Writes RAW: owns stages, raw tables and Snowpipes."
    TRANSFORMER = "Reads RAW, builds ANALYTICS (dbt prod) and DEV (dbt dev/CI); runs the forecast job."
    REPORTER    = "Read-only on ANALYTICS; used by the dashboard and analysts."
  }
}

# ---- Cost guardrails ---------------------------------------------------------------------

resource "snowflake_resource_monitor" "gridlens" {
  name            = "GRIDLENS_MONTHLY_RM"
  credit_quota    = var.monthly_credit_quota
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"

  notify_triggers           = [50, 75, 90]
  suspend_trigger           = 100 # finish running queries, then suspend
  suspend_immediate_trigger = 110 # kill running queries
  notify_users              = var.resource_monitor_notify_users
}

resource "snowflake_warehouse" "gridlens" {
  name                = "GRIDLENS_WH"
  warehouse_size      = "XSMALL"
  auto_suspend        = 60 # seconds; billing is per-second after the first minute
  auto_resume         = "true"
  initially_suspended = true
  resource_monitor    = snowflake_resource_monitor.gridlens.fully_qualified_name
  comment             = "Single XS warehouse for all gridlens workloads."
}

# ---- Databases ---------------------------------------------------------------------------

resource "snowflake_database" "this" {
  for_each = {
    RAW       = "Landing tables loaded by Snowpipe. Append-only."
    ANALYTICS = "dbt prod output (staging, intermediate, marts) and forecast outputs."
    DEV       = "dbt dev schemas (DBT_<user>) and CI schemas (CI_PR_<n>)."
  }
  name    = each.key
  comment = each.value
  # Time Travel is the main storage-cost lever; raw files remain in S3 anyway.
  data_retention_time_in_days = each.key == "ANALYTICS" ? 1 : 0
}

# ---- Roles (RBAC) ------------------------------------------------------------------------

resource "snowflake_account_role" "this" {
  for_each = local.roles
  name     = each.key
  comment  = each.value
}

# Custom roles roll up to SYSADMIN so admins can manage objects the roles create.
resource "snowflake_grant_account_role" "to_sysadmin" {
  for_each         = snowflake_account_role.this
  role_name        = each.value.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_service_user" "svc" {
  name              = var.snowflake_service_user
  login_name        = var.snowflake_service_user
  default_warehouse = snowflake_warehouse.gridlens.name
  default_role      = snowflake_account_role.this["TRANSFORMER"].name
  rsa_public_key    = var.snowflake_service_user_public_key
  comment           = "Airflow / CI service user (key-pair auth only)."
}

resource "snowflake_grant_account_role" "svc" {
  for_each  = toset(["LOADER", "TRANSFORMER"])
  role_name = snowflake_account_role.this[each.key].name
  user_name = snowflake_service_user.svc.name
}

resource "snowflake_grant_account_role" "reporters" {
  for_each  = toset(var.reporter_users)
  role_name = snowflake_account_role.this["REPORTER"].name
  user_name = each.key
}

# ---- Grants ------------------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "warehouse" {
  for_each          = snowflake_account_role.this
  account_role_name = each.value.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.gridlens.name
  }
}

locals {
  # role -> database -> privileges on the database itself
  database_grants = {
    "LOADER/RAW"            = ["USAGE", "CREATE SCHEMA"]
    "TRANSFORMER/RAW"       = ["USAGE"]
    "TRANSFORMER/ANALYTICS" = ["USAGE", "CREATE SCHEMA"]
    "TRANSFORMER/DEV"       = ["USAGE", "CREATE SCHEMA"]
    "REPORTER/ANALYTICS"    = ["USAGE"]
  }
  # Read access to everything created later in a database (dbt recreates tables constantly).
  read_grants = {
    "TRANSFORMER/RAW"    = true
    "REPORTER/ANALYTICS" = true
  }
}

resource "snowflake_grant_privileges_to_account_role" "database" {
  for_each          = local.database_grants
  account_role_name = snowflake_account_role.this[split("/", each.key)[0]].name
  privileges        = each.value
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.this[split("/", each.key)[1]].name
  }
}

resource "snowflake_grant_privileges_to_account_role" "future_schemas" {
  for_each          = local.read_grants
  account_role_name = snowflake_account_role.this[split("/", each.key)[0]].name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.this[split("/", each.key)[1]].name
  }
}

resource "snowflake_grant_privileges_to_account_role" "future_tables" {
  for_each          = local.read_grants
  account_role_name = snowflake_account_role.this[split("/", each.key)[0]].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.this[split("/", each.key)[1]].name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "future_views" {
  for_each          = local.read_grants
  account_role_name = snowflake_account_role.this[split("/", each.key)[0]].name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.this[split("/", each.key)[1]].name
    }
  }
}

# The stream + task (snowflake/02_stream_task.sql) run as TRANSFORMER.
resource "snowflake_grant_privileges_to_account_role" "execute_task" {
  account_role_name = snowflake_account_role.this["TRANSFORMER"].name
  privileges        = ["EXECUTE TASK"]
  on_account        = true
}

# ---- S3 storage integration --------------------------------------------------------------

resource "snowflake_storage_integration" "s3" {
  name                      = "GRIDLENS_S3_INT"
  type                      = "EXTERNAL_STAGE"
  storage_provider          = "S3"
  enabled                   = true
  storage_aws_role_arn      = local.snowflake_role_arn
  storage_allowed_locations = ["s3://${var.bucket_name}/"]
}

resource "snowflake_grant_privileges_to_account_role" "integration" {
  account_role_name = snowflake_account_role.this["LOADER"].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "INTEGRATION"
    object_name = snowflake_storage_integration.s3.name
  }
}
