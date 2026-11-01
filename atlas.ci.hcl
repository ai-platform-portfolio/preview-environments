// CI uses an Atlas bot; local Compose remains usable without a Cloud login.
atlas {
  cloud {
    org = "ai-platform-portfolio"
  }
}

env "ci" {
  dev = "docker://postgres/18.6/dev?search_path=public"

  migration {
    dir = "file://migrations"
  }

  test {
    migrate {
      src = ["tests/migrations.test.hcl"]
    }
  }
}
