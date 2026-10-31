// Local CLI configuration only. Kubernetes delivery uses AtlasMigration resources.
env "local" {
  url = getenv("DATABASE_URL")
  dev = getenv("DEV_DATABASE_URL")

  migration {
    dir = "file://migrations"
  }

  test {
    migrate {
      src = ["tests/migrations.test.hcl"]
    }
  }
}
