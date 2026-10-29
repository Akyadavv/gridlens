terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
    snowflake = {
      source = "snowflakedb/snowflake"
      # v1 resource names/attributes. v2 splits storage integrations into per-cloud
      # resources; bump deliberately and follow the provider's migration guide.
      version = "~> 1.2"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project    = "gridlens"
      managed_by = "terraform"
    }
  }
}

# Runs as an admin user with key-pair auth. Only Terraform uses ACCOUNTADMIN; every
# workload (ingestion, dbt, dashboard) uses the narrow roles created below.
provider "snowflake" {
  organization_name = var.snowflake_organization
  account_name      = var.snowflake_account
  user              = var.snowflake_admin_user
  role              = "ACCOUNTADMIN"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_admin_private_key_path)

  preview_features_enabled = ["snowflake_storage_integration_resource"]
}
