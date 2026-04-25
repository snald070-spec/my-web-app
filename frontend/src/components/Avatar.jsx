const COLORS = [
  "bg-blue-500", "bg-red-500", "bg-green-500", "bg-purple-500",
  "bg-amber-500", "bg-pink-500", "bg-teal-500", "bg-indigo-500",
];

function colorForName(name) {
  if (!name) return COLORS[0];
  let code = 0;
  for (let i = 0; i < name.length; i++) code += name.charCodeAt(i);
  return COLORS[code % COLORS.length];
}

export default function Avatar({ name, avatarUrl, size = "md", className = "" }) {
  const sizes = {
    sm:  "w-8  h-8  text-xs",
    md:  "w-11 h-11 text-sm",
    lg:  "w-16 h-16 text-xl",
    xl:  "w-20 h-20 text-2xl",
  };
  const ring = {
    sm: "ring-1",
    md: "ring-2",
    lg: "ring-2",
    xl: "ring-2",
  };
  const sizeClass = sizes[size] ?? sizes.md;
  const ringClass = ring[size] ?? ring.md;
  const initial   = (name || "?").charAt(0).toUpperCase();

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name || "avatar"}
        className={`rounded-full object-cover shrink-0 ${sizeClass} ${ringClass} ring-white ${className}`}
        onError={(e) => {
          e.currentTarget.style.display = "none";
          e.currentTarget.nextSibling && (e.currentTarget.nextSibling.style.display = "flex");
        }}
      />
    );
  }

  return (
    <div
      className={`rounded-full flex items-center justify-center shrink-0 font-bold text-white ${colorForName(name)} ${sizeClass} ${className}`}
    >
      {initial}
    </div>
  );
}
