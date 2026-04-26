<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Management - Glacier Console</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    "colors": {
                        "tertiary-fixed": "#ffdbcc",
                        "on-tertiary-fixed": "#351000",
                        "on-error-container": "#93000a",
                        "surface-bright": "#fcf8ff",
                        "on-surface": "#1b1b24",
                        "outline-variant": "#c7c4d8",
                        "on-surface-variant": "#464555",
                        "tertiary": "#7e3000",
                        "on-primary": "#ffffff",
                        "error": "#ba1a1a",
                        "primary-fixed-dim": "#c3c0ff",
                        "on-primary-container": "#dad7ff",
                        "secondary": "#565e74",
                        "outline": "#777587",
                        "on-secondary-container": "#5c647a",
                        "primary-container": "#4f46e5",
                        "inverse-surface": "#302f39",
                        "surface-container": "#f0ecf9",
                        "inverse-on-surface": "#f3effc",
                        "error-container": "#ffdad6",
                        "secondary-fixed-dim": "#bec6e0",
                        "on-primary-fixed": "#0f0069",
                        "on-tertiary": "#ffffff",
                        "primary": "#3525cd",
                        "surface-container-low": "#f5f2ff",
                        "inverse-primary": "#c3c0ff",
                        "tertiary-fixed-dim": "#ffb695",
                        "on-background": "#1b1b24",
                        "on-secondary-fixed-variant": "#3f465c",
                        "background": "#fcf8ff",
                        "tertiary-container": "#a44100",
                        "surface": "#fcf8ff",
                        "on-error": "#ffffff",
                        "secondary-container": "#dae2fd",
                        "surface-variant": "#e4e1ee",
                        "surface-dim": "#dcd8e5",
                        "secondary-fixed": "#dae2fd",
                        "surface-container-high": "#eae6f4",
                        "on-tertiary-container": "#ffd2be",
                        "on-secondary": "#ffffff",
                        "surface-tint": "#4d44e3",
                        "on-secondary-fixed": "#131b2e",
                        "on-primary-fixed-variant": "#3323cc",
                        "on-tertiary-fixed-variant": "#7b2f00",
                        "surface-container-highest": "#e4e1ee",
                        "surface-container-lowest": "#ffffff",
                        "primary-fixed": "#e2dfff"
                    },
                    "borderRadius": {
                        "DEFAULT": "0.25rem",
                        "lg": "0.5rem",
                        "xl": "0.75rem",
                        "full": "9999px"
                    },
                    "spacing": {
                        "margin": "32px",
                        "bento-gap": "16px",
                        "unit": "4px",
                        "gutter": "24px",
                        "container-padding": "24px"
                    },
                    "fontFamily": {
                        "h1": ["Inter"],
                        "body-sm": ["Inter"],
                        "body-base": ["Inter"],
                        "display": ["Inter"],
                        "mono-label": ["Inter"],
                        "label-caps": ["Inter"],
                        "h2": ["Inter"]
                    },
                    "fontSize": {
                        "h1": ["30px", { "lineHeight": "1.2", "letterSpacing": "-0.02em", "fontWeight": "600" }],
                        "body-sm": ["13px", { "lineHeight": "1.5", "letterSpacing": "0", "fontWeight": "400" }],
                        "body-base": ["14px", { "lineHeight": "1.5", "letterSpacing": "0", "fontWeight": "400" }],
                        "display": ["48px", { "lineHeight": "1.1", "letterSpacing": "-0.02em", "fontWeight": "600" }],
                        "mono-label": ["12px", { "lineHeight": "1", "letterSpacing": "-0.01em", "fontWeight": "500" }],
                        "label-caps": ["11px", { "lineHeight": "1", "letterSpacing": "0.05em", "fontWeight": "600" }],
                        "h2": ["24px", { "lineHeight": "1.3", "letterSpacing": "-0.01em", "fontWeight": "600" }]
                    }
                }
            }
        }
    </script>
<style>
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        .icon-fill {
            font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        /* Custom scrollbar for data dense tables */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: #e4e1ee;
            border-radius: 9999px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #c7c4d8;
        }
    </style>
</head>
<body class="bg-background text-on-background font-body-base antialiased min-h-screen flex selection:bg-primary-fixed selection:text-on-primary-fixed">
<!-- SideNavBar Component -->
<nav class="fixed left-0 top-0 h-screen w-64 border-r border-slate-200/50 bg-white/70 backdrop-blur-xl shadow-sm flex flex-col h-full p-4 font-inter text-sm antialiased z-50">
<!-- Header -->
<div class="flex items-center gap-3 px-2 mb-8 mt-2">
<div class="w-10 h-10 rounded-lg bg-gradient-to-br from-primary-container to-primary flex items-center justify-center text-on-primary font-bold shadow-sm">
                G
            </div>
<div>
<h1 class="text-xl font-black tracking-tight text-slate-900">Glacier Console</h1>
<p class="text-xs text-on-surface-variant font-medium">Enterprise Tier</p>
</div>
</div>
<!-- Main Navigation -->
<div class="flex-1 space-y-1">
<a class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-indigo-600 transition-all rounded-lg hover:translate-y-[-1px] transition-transform duration-200 hover:bg-surface-container-low" href="#">
<span class="material-symbols-outlined text-xl">dashboard</span>
<span class="font-medium">Dashboard</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-indigo-600 font-semibold bg-indigo-50/50 rounded-lg transition-all scale-95 duration-150" href="#">
<span class="material-symbols-outlined text-xl icon-fill">settings</span>
<span>Management</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-indigo-600 transition-all rounded-lg hover:translate-y-[-1px] transition-transform duration-200 hover:bg-surface-container-low" href="#">
<span class="material-symbols-outlined text-xl">person</span>
<span class="font-medium">Profile</span>
</a>
</div>
<!-- Footer Actions -->
<div class="mt-auto space-y-1 pt-4 border-t border-slate-200/50">
<a class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-indigo-600 transition-all rounded-lg hover:translate-y-[-1px] transition-transform duration-200 hover:bg-surface-container-low" href="#">
<span class="material-symbols-outlined text-xl">settings</span>
<span class="font-medium">Settings</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-indigo-600 transition-all rounded-lg hover:translate-y-[-1px] transition-transform duration-200 hover:bg-surface-container-low" href="#">
<span class="material-symbols-outlined text-xl">logout</span>
<span class="font-medium">Logout</span>
</a>
<div class="mt-4 px-2">
<button class="w-full py-2.5 px-4 bg-surface-bright border border-outline-variant text-on-surface font-mono-label text-mono-label rounded-lg hover:bg-surface-container transition-colors shadow-sm flex items-center justify-center gap-2">
<span class="material-symbols-outlined text-sm">support_agent</span>
                    Contact Support
                </button>
</div>
<!-- User Profile Snippet Footer -->
<div class="mt-4 px-2 flex items-center gap-3 py-2">
<img alt="Glacier Admin" class="w-8 h-8 rounded-full ring-2 ring-surface-container" data-alt="Professional headshot of a man with short hair wearing a dark shirt against a blurred office background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuA10G_2x9bpLkk_9nAYpWNugGEX7wItCAfXHK61K3maQg3GYVx1lJbPhsePguFh7X7ydJzV07W_yclzlNP_jRJseJecUoRIJkU-fNu6bQmGKaadZxmQMy8hzh_iKdLP4jc5KtAWOE4lZDO5sdmvzJBPtEMDMVvhETCxOES9N51WyXM7uIfsmxskuBfmdMe5JR-uWJ0LRjwvUcH-BASvgxs3S6oYEu5tUE8ve6_tw1FYO-U7qTrk0ZxvxMUc6j-EHOfVZel1Poelfv0"/>
<div class="flex-1 min-w-0">
<p class="text-sm font-medium text-on-surface truncate">Admin User</p>
<p class="text-xs text-on-surface-variant truncate">admin@glacier.io</p>
</div>
</div>
</div>
</nav>
<!-- Main Content Canvas -->
<main class="flex-1 ml-64 min-h-screen flex flex-col">
<!-- TopNavBar Component -->
<header class="sticky top-0 z-40 w-full border-b border-white/20 bg-white/60 backdrop-blur-2xl shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] flex justify-between items-center px-8 h-16 font-inter tracking-tight">
<div class="flex items-center gap-8 h-full">
<h2 class="text-lg font-bold text-slate-900">Management</h2>
<nav class="hidden md:flex h-full gap-6">
<a class="text-indigo-600 font-bold border-b-2 border-indigo-600 pb-4 mt-4 hover:text-indigo-500 transition-colors duration-200 flex items-center h-full pt-4" href="#">User &amp; Tokens</a>
<a class="text-slate-500 pb-4 mt-4 hover:text-indigo-500 transition-colors duration-200 flex items-center h-full pt-4" href="#">Usage Analytics</a>
</nav>
</div>
<div class="flex items-center gap-4">
<div class="relative hidden lg:block">
<span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-sm">search</span>
<input class="w-64 pl-9 pr-4 py-1.5 bg-surface-bright border border-outline-variant rounded-full text-sm focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container transition-all shadow-sm" placeholder="Search resources..." type="text"/>
</div>
<div class="flex items-center gap-2 border-l border-outline-variant/30 pl-4 ml-2">
<button class="p-1.5 text-on-surface-variant hover:text-primary-container hover:bg-surface-container rounded-full transition-colors relative">
<span class="material-symbols-outlined">account_balance_wallet</span>
</button>
<button class="p-1.5 text-on-surface-variant hover:text-primary-container hover:bg-surface-container rounded-full transition-colors relative">
<span class="material-symbols-outlined">notifications</span>
<span class="absolute top-1 right-1.5 w-2 h-2 bg-error rounded-full"></span>
</button>
<img alt="User Profile" class="w-8 h-8 rounded-full ml-2 border border-outline-variant/30" data-alt="Professional headshot of a man with short hair wearing a dark shirt against a blurred office background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCDCSQzkmbJgcg5L_SIQNoA9vOVqnjakTcbaR4QiiyTxnqJ-B9XuBTWbMDhNX8ei7QQIeBWfynedzsi7Ii-CFlgN1Pq8UHPRnTP9GmPpLIeVVWAA_NM7LjBJPVXlgm9F1MuAyn99qEIsJdTaS6mnYiczzGfnXlDPMcYrxoeA5nzEZGjEv6Qd5M1NsN7BdSaTBZMgvhIy5AW4a_b4pJe7iXcYtE1hNON8SLbSexkdp35U9Qkw92XQ6dpIpPbw1PJ7uQW6TKxndtfuVs"/>
</div>
</div>
</header>
<!-- Canvas Body -->
<div class="flex-1 p-margin overflow-y-auto">
<!-- Page Header area -->
<div class="mb-8 flex justify-between items-end">
<div>
<h1 class="font-h1 text-h1 text-on-surface mb-2">User &amp; Tokens</h1>
<p class="font-body-base text-body-base text-on-surface-variant max-w-2xl">Manage organization members, their access roles, and monitor API key generation and usage limits. Credit consumption is tracked at the organizational level.</p>
</div>
<div class="flex gap-3">
<button class="px-4 py-2 bg-surface-bright border border-outline-variant text-on-surface rounded-lg font-mono-label text-mono-label shadow-[0_2px_4px_rgba(0,0,0,0.02)] hover:-translate-y-[1px] transition-transform flex items-center gap-2">
<span class="material-symbols-outlined text-sm">download</span>
                        Export CSV
                    </button>
<button class="px-4 py-2 bg-primary-container text-on-primary rounded-lg font-mono-label text-mono-label shadow-[0_2px_8px_rgba(79,70,229,0.2)] hover:-translate-y-[1px] transition-transform flex items-center gap-2">
<span class="material-symbols-outlined text-sm">person_add</span>
                        Invite User
                    </button>
</div>
</div>
<!-- Bento Grid Layout -->
<div class="grid grid-cols-12 gap-bento-gap">
<!-- Quick Stats -->
<div class="col-span-12 grid grid-cols-3 gap-bento-gap mb-4">
<div class="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
<div class="flex justify-between items-start mb-2">
<span class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Total Users</span>
<span class="material-symbols-outlined text-outline text-xl">group</span>
</div>
<div class="font-display text-display text-on-surface">124</div>
<div class="text-xs text-on-surface-variant mt-1 flex items-center gap-1">
<span class="text-emerald-600 font-medium flex items-center"><span class="material-symbols-outlined text-[14px]">trending_up</span> 12%</span> vs last month
                        </div>
</div>
<div class="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80 relative overflow-hidden">
<div class="absolute top-0 right-0 w-32 h-32 bg-sky-100 rounded-full blur-3xl opacity-50 -mr-10 -mt-10 pointer-events-none"></div>
<div class="flex justify-between items-start mb-2 relative z-10">
<span class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Active Tokens</span>
<span class="material-symbols-outlined text-sky-600 text-xl">key</span>
</div>
<div class="font-display text-display text-on-surface relative z-10">892</div>
<div class="text-xs text-on-surface-variant mt-1 relative z-10 flex items-center gap-1">
                            Across 45 active projects
                        </div>
</div>
<div class="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
<div class="flex justify-between items-start mb-2">
<span class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Avg Credits / User</span>
<span class="material-symbols-outlined text-outline text-xl">data_usage</span>
</div>
<div class="font-display text-display text-on-surface">45.2k</div>
<div class="text-xs text-on-surface-variant mt-1 flex items-center gap-1">
<span class="text-error font-medium flex items-center"><span class="material-symbols-outlined text-[14px]">trending_down</span> 3%</span> vs last month
                        </div>
</div>
</div>
<!-- Main Data Table - Spans full width -->
<div class="col-span-12 bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden flex flex-col">
<!-- Table Header Actions -->
<div class="p-4 border-b border-outline-variant/30 flex justify-between items-center bg-surface-lowest/50">
<div class="flex items-center gap-4">
<div class="relative">
<span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-sm">search</span>
<input class="pl-9 pr-4 py-1.5 bg-surface-bright border border-outline-variant rounded-md text-sm focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container transition-all w-64 shadow-sm" placeholder="Filter users..." type="text"/>
</div>
<button class="px-3 py-1.5 bg-surface-bright border border-outline-variant text-on-surface rounded-md font-mono-label text-mono-label flex items-center gap-2 hover:bg-surface-container transition-colors">
<span class="material-symbols-outlined text-sm">filter_list</span>
                                Status: All
                            </button>
</div>
<div class="text-xs text-on-surface-variant font-medium">Showing 1-5 of 124 users</div>
</div>
<!-- Table structure -->
<div class="overflow-x-auto">
<table class="w-full text-left border-collapse">
<thead>
<tr class="bg-surface-container-low/50 border-b border-outline-variant/30">
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold w-12"></th>
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold">User Details</th>
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold">Role</th>
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold">Status</th>
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold text-right">30d Credits</th>
<th class="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider font-semibold text-right">Actions</th>
</tr>
</thead>
<tbody class="font-body-sm text-body-sm text-on-surface divide-y divide-outline-variant/20">
<!-- Row 1: Expanded State -->
<tr class="hover:bg-surface-container-lowest transition-colors bg-sky-50/30">
<td class="py-4 px-6 align-top pt-5 text-center">
<button class="text-primary-container hover:bg-primary-container/10 rounded-full p-0.5 transition-colors">
<span class="material-symbols-outlined text-lg">expand_more</span>
</button>
</td>
<td class="py-4 px-6 align-top">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">SJ</div>
<div>
<div class="font-medium text-on-surface">Sarah Jenkins</div>
<div class="text-on-surface-variant text-xs mt-0.5">sarah.j@company.com</div>
</div>
</div>
</td>
<td class="py-4 px-6 align-top pt-5">
<span class="px-2 py-1 bg-surface-container text-on-surface font-mono-label text-[10px] rounded border border-outline-variant/50">Admin</span>
</td>
<td class="py-4 px-6 align-top pt-5">
<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100/50 text-emerald-800 text-xs font-medium border border-emerald-200/50">
<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                            Active
                                        </span>
</td>
<td class="py-4 px-6 align-top pt-5 text-right font-mono-label text-on-surface">
                                        124,500
                                    </td>
<td class="py-4 px-6 align-top pt-4 text-right">
<button class="p-1.5 text-on-surface-variant hover:text-primary-container hover:bg-surface-container rounded transition-colors">
<span class="material-symbols-outlined text-sm">more_vert</span>
</button>
</td>
</tr>
<!-- Nested API Keys Sub-table for Row 1 -->
<tr class="bg-surface-container-lowest border-b-2 border-primary-container/20">
<td class="p-0" colspan="6">
<div class="px-12 py-6 pl-20 bg-gradient-to-b from-sky-50/20 to-transparent">
<div class="flex justify-between items-center mb-4">
<h4 class="font-mono-label text-mono-label text-on-surface font-semibold flex items-center gap-2">
<span class="material-symbols-outlined text-sm text-sky-600">key</span>
                                                    Active API Keys
                                                </h4>
<button class="text-xs font-medium text-primary-container hover:text-primary flex items-center gap-1">
<span class="material-symbols-outlined text-[14px]">add</span> Generate New Key
                                                </button>
</div>
<div class="border border-outline-variant/40 rounded-lg overflow-hidden bg-white">
<table class="w-full text-left text-xs">
<thead class="bg-surface-container-low/50">
<tr>
<th class="py-2 px-4 font-medium text-on-surface-variant w-1/3">Key Name</th>
<th class="py-2 px-4 font-medium text-on-surface-variant font-mono">Token Secret</th>
<th class="py-2 px-4 font-medium text-on-surface-variant">Last Used</th>
<th class="py-2 px-4 font-medium text-on-surface-variant text-right">Status</th>
</tr>
</thead>
<tbody class="divide-y divide-outline-variant/20">
<tr>
<td class="py-3 px-4 text-on-surface font-medium flex items-center gap-2">
                                                                Production App
                                                                <span class="px-1.5 py-0.5 bg-surface-container rounded text-[9px] text-on-surface-variant uppercase tracking-wide">Prod</span>
</td>
<td class="py-3 px-4 font-mono text-on-surface-variant flex items-center gap-2">
                                                                sk-proj-...8f92
                                                                <button class="text-outline hover:text-primary-container transition-colors" title="Copy to clipboard">
<span class="material-symbols-outlined text-[14px]">content_copy</span>
</button>
</td>
<td class="py-3 px-4 text-on-surface-variant">2 mins ago</td>
<td class="py-3 px-4 text-right">
<!-- Toggle switch -->
<button class="relative inline-flex h-5 w-9 items-center rounded-full bg-primary-container transition-colors focus:outline-none focus:ring-2 focus:ring-primary-container focus:ring-offset-2">
<span class="translate-x-5 inline-block h-3 w-3 transform rounded-full bg-white transition-transform"></span>
</button>
</td>
</tr>
<tr>
<td class="py-3 px-4 text-on-surface font-medium flex items-center gap-2">
                                                                Local Dev Environment
                                                                <span class="px-1.5 py-0.5 bg-surface-container rounded text-[9px] text-on-surface-variant uppercase tracking-wide">Dev</span>
</td>
<td class="py-3 px-4 font-mono text-on-surface-variant flex items-center gap-2">
                                                                sk-proj-...2a4b
                                                                <button class="text-outline hover:text-primary-container transition-colors" title="Copy to clipboard">
<span class="material-symbols-outlined text-[14px]">content_copy</span>
</button>
</td>
<td class="py-3 px-4 text-on-surface-variant">Yesterday, 4:23 PM</td>
<td class="py-3 px-4 text-right">
<button class="relative inline-flex h-5 w-9 items-center rounded-full bg-outline-variant transition-colors focus:outline-none focus:ring-2 focus:ring-primary-container focus:ring-offset-2">
<span class="translate-x-1 inline-block h-3 w-3 transform rounded-full bg-white transition-transform"></span>
</button>
</td>
</tr>
</tbody>
</table>
</div>
</div>
</td>
</tr>
<!-- Row 2 -->
<tr class="hover:bg-surface-container-lowest transition-colors cursor-pointer group">
<td class="py-4 px-6 text-center">
<button class="text-outline group-hover:text-primary-container hover:bg-surface-container rounded-full p-0.5 transition-colors">
<span class="material-symbols-outlined text-lg">chevron_right</span>
</button>
</td>
<td class="py-4 px-6">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">MR</div>
<div>
<div class="font-medium text-on-surface">Michael Ross</div>
<div class="text-on-surface-variant text-xs mt-0.5">m.ross@company.com</div>
</div>
</div>
</td>
<td class="py-4 px-6">
<span class="px-2 py-1 bg-surface-container text-on-surface font-mono-label text-[10px] rounded border border-outline-variant/50">Developer</span>
</td>
<td class="py-4 px-6">
<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100/50 text-emerald-800 text-xs font-medium border border-emerald-200/50">
<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                            Active
                                        </span>
</td>
<td class="py-4 px-6 text-right font-mono-label text-on-surface">
                                        85,200
                                    </td>
<td class="py-4 px-6 text-right">
<button class="p-1.5 text-on-surface-variant hover:text-primary-container hover:bg-surface-container rounded transition-colors">
<span class="material-symbols-outlined text-sm">more_vert</span>
</button>
</td>
</tr>
<!-- Row 3 -->
<tr class="hover:bg-surface-container-lowest transition-colors cursor-pointer group">
<td class="py-4 px-6 text-center">
<button class="text-outline group-hover:text-primary-container hover:bg-surface-container rounded-full p-0.5 transition-colors">
<span class="material-symbols-outlined text-lg">chevron_right</span>
</button>
</td>
<td class="py-4 px-6">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">AZ</div>
<div>
<div class="font-medium text-on-surface">Alex Zhang</div>
<div class="text-on-surface-variant text-xs mt-0.5">alex.z@company.com</div>
</div>
</div>
</td>
<td class="py-4 px-6">
<span class="px-2 py-1 bg-surface-container text-on-surface font-mono-label text-[10px] rounded border border-outline-variant/50">Developer</span>
</td>
<td class="py-4 px-6">
<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-variant text-on-surface-variant text-xs font-medium border border-outline-variant/50">
<span class="w-1.5 h-1.5 rounded-full bg-outline"></span>
                                            Inactive
                                        </span>
</td>
<td class="py-4 px-6 text-right font-mono-label text-on-surface-variant">
                                        0
                                    </td>
<td class="py-4 px-6 text-right">
<button class="p-1.5 text-on-surface-variant hover:text-primary-container hover:bg-surface-container rounded transition-colors">
<span class="material-symbols-outlined text-sm">more_vert</span>
</button>
</td>
</tr>
</tbody>
</table>
</div>
<!-- Table Footer Pagination -->
<div class="p-4 border-t border-outline-variant/30 flex justify-between items-center bg-surface-lowest/50">
<button class="px-3 py-1.5 border border-outline-variant rounded-md text-sm text-on-surface-variant hover:bg-surface-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed" disabled="">Previous</button>
<div class="flex items-center gap-1">
<button class="w-8 h-8 flex items-center justify-center rounded-md bg-primary-container text-on-primary text-sm font-medium">1</button>
<button class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface-container text-on-surface-variant text-sm font-medium transition-colors">2</button>
<button class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface-container text-on-surface-variant text-sm font-medium transition-colors">3</button>
<span class="text-on-surface-variant px-1">...</span>
<button class="w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface-container text-on-surface-variant text-sm font-medium transition-colors">12</button>
</div>
<button class="px-3 py-1.5 border border-outline-variant rounded-md text-sm text-on-surface-variant hover:bg-surface-container transition-colors">Next</button>
</div>
</div>
</div>
<!-- Decorative Bottom Gradient for airy feel -->
<div class="h-32 w-full bg-gradient-to-t from-s ky-50/30 to-transparent mt-8 rounded-b-3xl pointer-events-none"></div>
</div>
</main>
</body></html>