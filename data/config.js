// Public connection details for the shared shortlist (Supabase). The anon key is designed to be public:
// it can only call the passcode-protected functions in supabase/migrations/*.sql, never read the tables.
window.SYNC_CONFIG = {
  url: "https://xkryhtehfjgaofnqpxfi.supabase.co",
  key: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhrcnlodGVoZmpnYW9mbnFweGZpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA3OTAyMzEsImV4cCI6MjEwNjM2NjIzMX0.6OxMXUx_SuSdZduorZxPPmVVOKNXDTPa5zXUWzCzXm8"
};
