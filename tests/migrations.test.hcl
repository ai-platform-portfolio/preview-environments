test "migrate" "messages" {
  migrate {
    to = "20261031233000"
  }

  exec {
    sql = "INSERT INTO public.messages (id, text) VALUES ('00000000-0000-0000-0000-000000000001', 'Seeded message')"
  }

  assert {
    sql = "SELECT text = 'Seeded message' AND created_at IS NOT NULL FROM public.messages WHERE id = '00000000-0000-0000-0000-000000000001'"
  }

  catch {
    sql   = "INSERT INTO public.messages (id, text) VALUES ('00000000-0000-0000-0000-000000000002', '   ')"
    error = "violates check constraint"
  }

  catch {
    sql   = "INSERT INTO public.messages (id, text) VALUES ('00000000-0000-0000-0000-000000000003', repeat('x', 501))"
    error = "value too long"
  }
}
