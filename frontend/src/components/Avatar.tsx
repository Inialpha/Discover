import { API_URL } from "../api";

export const PALETTES = [
  { bg: "#E8F0FE", fig: "#4F6BED", ink: "#2B2F77" }, { bg: "#FDECEA", fig: "#E0574F", ink: "#6B2420" },
  { bg: "#E6F6EC", fig: "#2E9E5B", ink: "#14502D" }, { bg: "#FFF4E0", fig: "#E59A1F", ink: "#6E4608" },
  { bg: "#F1E8FB", fig: "#8A56D6", ink: "#43257A" }, { bg: "#E3F4F7", fig: "#1C93A8", ink: "#0D4A56" },
];
export const paletteOf = (key: string) => PALETTES[(parseInt(key.split("-")[2] ?? "0", 10) || 0) % PALETTES.length];

export default function Avatar({ avatarKey, size = 88, alt = "" }: { avatarKey: string; size?: number; alt?: string }) {
  return <img className="avatar" src={`${API_URL}/api/avatars/${avatarKey}.svg`} width={size} height={size} alt={alt} />;
}
