import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/companies", label: "Companies" },
  { to: "/email-queue", label: "Email Queue" },
  { to: "/profile", label: "Profile" }
];

export default function Sidebar() {
  return (
    <aside className="flex h-full w-64 flex-col border-r border-slate-800 bg-slate-950 p-6">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Lead Finder</p>
        <h1 className="mt-2 text-xl font-semibold text-white">Operations</h1>
      </div>

      <nav className="space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                "block rounded-lg px-3 py-2 text-sm font-medium transition",
                isActive
                  ? "bg-slate-800 text-white"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
              ].join(" ")
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
