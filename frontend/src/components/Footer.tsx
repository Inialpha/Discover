const TEAM = (import.meta.env.VITE_TEAM_NAME as string | undefined) || "the Discover team";
const EMAIL = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined) || "";

export default function Footer() {
  return (
    <footer className="foot">
      <p>
        <b>Discover</b> turns a product description into audience personas grounded in real market taste data.
        Built for the Qloo Hackathon. Qloo supplies the taste data. Anything marked Suggestion is not confirmed by data.
      </p>
      <p>
        © {new Date().getFullYear()} {TEAM}.
        {EMAIL && <> Contact: <a href={`mailto:${EMAIL}`}>{EMAIL}</a></>}
      </p>
    </footer>
  );
}
