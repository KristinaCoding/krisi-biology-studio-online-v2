from pathlib import Path
p=Path(__file__).with_name('portal.py')
s=p.read_text(encoding='utf-8')
if 'dashboard-layout' in s:
    raise SystemExit('Dashboard redesign already applied; no changes made.')
old="'<style>' + css + '</style></head><body>'"
new="'<style>' + css + '</style><link rel=\"stylesheet\" href=\"/static/dashboard_v2.css\"></head><body>'"
assert old in s
s=s.replace(old,new,1)
old='    return page("Teacher dashboard",body)'
new='''    body = (\n        '<div class="dashboard-layout"><nav class="dashboard-nav" aria-label="Teacher navigation">'\n        '<small>TEACHER WORKSPACE</small>'\n        '<a href="#section-1">Invite students</a><a href="#section-2">Lessons</a>'\n        '<a href="#section-3">Quizzes</a><a href="#section-4">Results</a>'\n        '<a href="#section-5">Bookings</a></nav><div class="dashboard-main">'\n        '<p class="dashboard-intro">Your teaching workspace · Manage lessons and learning in one place.</p>'\n        '<div class="dashboard-stats">'\n        f'<div class="stat-card"><strong>{len(students)}</strong><span>Students</span></div>'\n        f'<div class="stat-card"><strong>{len(results)}</strong><span>Quiz results</span></div>'\n        f'<div class="stat-card"><strong>{len(bookings)}</strong><span>Bookings</span></div>'\n        '</div><div class="dashboard-panels">'\n        + body.replace('<article>', '<article>', 1)\n        + '</div></div></div>'\n    )\n    for index in range(1, 6):\n        body = body.replace('<article>', f'<article id="section-{index}">', 1)\n    return page("Teacher dashboard",body)'''
# Assign ids in order by replacing first untagged article on each pass
assert old in s
s=s.replace(old,new,1)
old='    return page("Student portal",body)'
new='''    body = (\n        '<div class="dashboard-layout"><nav class="dashboard-nav" aria-label="Student navigation">'\n        '<small>STUDENT WORKSPACE</small><a href="#section-1">My lessons</a>'\n        '<a href="#section-2">My quizzes</a><a href="#section-3">Book a lesson</a>'\n        '</nav><div class="dashboard-main">'\n        '<p class="dashboard-intro">Your learning space · Lessons, quizzes and bookings.</p>'\n        '<div class="dashboard-stats">'\n        f'<div class="stat-card"><strong>{len(lessons)}</strong><span>Lessons</span></div>'\n        f'<div class="stat-card"><strong>{len(quizzes)}</strong><span>Quizzes</span></div>'\n        f'<div class="stat-card"><strong>{len(bookings)}</strong><span>Bookings</span></div>'\n        '</div><div class="dashboard-panels">' + body + '</div></div></div>'\n    )\n    for index in range(1, 4):\n        body = body.replace('<article>', f'<article id="section-{index}">', 1)\n    return page("Student portal",body)'''
assert old in s
s=s.replace(old,new,1)
compile(s,str(p),'exec')
backup=p.with_name('portal_before_redesign.py')
if not backup.exists(): backup.write_text(p.read_text(encoding='utf-8'),encoding='utf-8')
p.write_text(s,encoding='utf-8')
print('PASS: Dashboard redesign applied. Backup: portal_before_redesign.py')
