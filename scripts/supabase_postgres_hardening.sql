-- Fotoce : durcissement Supabase quand PostgreSQL sert UNIQUEMENT Django (pas PostgREST / pas client Supabase direct).
--
-- Contexte : l’Advisor signale « RLS Disabled in Public » car le schéma public est exposé par défaut
-- aux rôles Supabase `anon` et `authenticated`. Django se connecte en postgres (superuser) : RLS ne
-- bloque pas l’app, mais bloque l’accès accidentel via l’API Supabase / clés publishable.
--
-- À exécuter une fois : Supabase Dashboard → SQL Editor → New query → Run.
-- Réversible : voir section « Rollback » en bas.
--
-- Prérequis : aucune app front/mobile ne lit la DB via supabase-js + clé anon sur ces tables.

BEGIN;

-- 1) Activer RLS sur toutes les tables du schéma public (sans policy = deny pour anon/authenticated)
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT quote_ident(schemaname) AS sn, quote_ident(tablename) AS tn
    FROM pg_tables
    WHERE schemaname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE %s.%s ENABLE ROW LEVEL SECURITY', r.sn, r.tn);
    EXECUTE format('ALTER TABLE %s.%s FORCE ROW LEVEL SECURITY', r.sn, r.tn);
  END LOOP;
END $$;

-- 2) Retirer les droits directs anon/authenticated (PostgREST)
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON ROUTINES FROM anon, authenticated;

COMMIT;

-- Vérification (doit lister rls_enabled = true pour vos tables Django) :
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Rollback (déconseillé en prod) :
-- ALTER TABLE public.<table> DISABLE ROW LEVEL SECURITY;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon, authenticated;
