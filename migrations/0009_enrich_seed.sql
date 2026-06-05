-- 0009 enrich seed data: fees, processing times, requirements, indigenous notes.

-- ── Forms: add fees and requirements ────────────────────────────────────────
UPDATE forms SET
    fee = 'Varies by licence class — check MVR fee schedule',
    requirements_json = '["Current interstate or overseas licence (to surrender)","Proof of identity — 100 points (e.g. passport or birth certificate)","Proof of NT residential address (utility bill or lease)"]'
WHERE url LIKE '%converting-interstate-licence%';

UPDATE forms SET
    fee = 'Free for volunteers; fee applies for paid workers — check Territory Families',
    requirements_json = '["100 points of ID (primary + secondary documents)","Completed application form"]'
WHERE url LIKE '%ochre-card%apply%';

UPDATE forms SET
    fee = 'Free for volunteers; renewal fee for paid workers',
    requirements_json = '["Current Ochre Card (expiring)","100 points of ID"]'
WHERE url LIKE '%ochre-card%renew%';

UPDATE forms SET
    fee = '~$42.90 (check current NT Police fee schedule)',
    requirements_json = '["100 points of certified ID","Completed application form","Payment"]'
WHERE url LIKE '%police-check%';

UPDATE forms SET
    fee = 'Varies by licence class — check NT Police licensing fee schedule',
    requirements_json = '["Certificate II in Security Operations (or equivalent)","National Police Certificate (less than 3 months old)","100 points of ID","Completed application form"]'
WHERE url LIKE '%security-licenc%';

UPDATE forms SET
    fee = 'Free',
    requirements_json = '["Proof of birth (hospital notification or statutory declaration)","Parent/guardian ID"]'
WHERE url LIKE '%register-a-birth%';

UPDATE forms SET
    fee = '$50.50 per certificate (standard) — check BDM fee schedule',
    requirements_json = '["Completed application form","Proof of entitlement (you must be the person, parent, or have authorisation)","Payment"]'
WHERE url LIKE '%birth-certificate%';

UPDATE forms SET
    fee = '$98.20 application fee (check BDM for current rate)',
    requirements_json = '["Completed application form","100 points of ID","Statutory declaration of reason for name change","Payment"]'
WHERE url LIKE '%change-of-name%';

UPDATE forms SET
    fee = '$50.50 per certificate',
    requirements_json = '["Completed application form","Proof of entitlement","Payment"]'
WHERE url LIKE '%marriages%' AND title LIKE '%Marriage Certificate%';

UPDATE forms SET
    fee = 'Varies — check Department of Infrastructure fee schedule',
    requirements_json = '["Architectural drawings and site plan","Licensed building certifier engaged","Completed application form","Payment"]'
WHERE url LIKE '%building-permit%';

UPDATE forms SET
    fee = 'Varies by project value — check Department of Infrastructure',
    requirements_json = '["Proof of land ownership","Owner-builder course certificate (for larger projects)","Completed application form"]'
WHERE url LIKE '%owner-builder%';

UPDATE forms SET
    fee = 'Lodgement fee varies by development type — check NT Planning',
    requirements_json = '["Site plan and drawings","Planning report","Completed DA form","Payment"]'
WHERE url LIKE '%development-applications%';

UPDATE forms SET
    fee = 'Stamp duty applies on property transfers — check Territory Revenue',
    requirements_json = '["Transfer document","Proof of identity for both parties","Stamped transfer form","Payment of stamp duty"]'
WHERE url LIKE '%transfer-land%';

UPDATE forms SET
    fee = '$55/year desexed; $110/year undesexed (discounts for pension holders)',
    requirements_json = '["Dog microchip number","Evidence of desexing (if applicable)","Owner contact details"]'
WHERE url LIKE '%animals%' AND title LIKE '%Dog%';

UPDATE forms SET
    fee = 'Varies — check NT WorkSafe fee schedule',
    requirements_json = '["Qualification certificate for the relevant high-risk work","Identity documents","Completed application form","Payment"]'
WHERE url LIKE '%worksafe%' AND url LIKE '%apply%';

UPDATE forms SET
    fee = 'Free to lodge',
    requirements_json = '["Injury report from workplace","Medical certificate from treating doctor","Completed claim form","Employer details"]'
WHERE url LIKE '%worksafe%' AND url LIKE '%claim%';

-- ── How-To Guides: add processing times, fees, indigenous notes ──────────────
UPDATE howto_guides SET
    fee = 'Varies by licence class — check MVR fee schedule',
    processing_time = 'Issued on the spot at an MVR office',
    indigenous_note = ''
WHERE title LIKE '%convert%interstate%' OR title LIKE '%interstate%licence%';

UPDATE howto_guides SET
    fee = 'Free for volunteers; fee for paid workers',
    processing_time = '2–6 weeks',
    indigenous_note = 'Different working-with-children arrangements may apply in certain remote and Indigenous community contexts. Contact Territory Families or your Land Council for advice.'
WHERE title LIKE '%Ochre Card%';

UPDATE howto_guides SET
    fee = '~$42.90 (check current schedule with NT Police)',
    processing_time = '5–10 business days',
    indigenous_note = ''
WHERE title LIKE '%police check%';

UPDATE howto_guides SET
    fee = 'Varies by licence class',
    processing_time = '4–6 weeks — do not start work until licence is received',
    indigenous_note = ''
WHERE title LIKE '%security%licence%';

UPDATE howto_guides SET
    fee = '$55/year desexed; $110/year undesexed',
    processing_time = 'Same day (online or in person at Council)',
    indigenous_note = ''
WHERE title LIKE '%dog%darwin%' OR title LIKE '%register%dog%';

UPDATE howto_guides SET
    fee = 'Varies — check Department of Infrastructure fee schedule',
    processing_time = '10 business days (may vary by certifier and project complexity)',
    indigenous_note = ''
WHERE title LIKE '%building permit%';

UPDATE howto_guides SET
    fee = 'Rates vary by property value and category',
    processing_time = 'Rates notice issued annually; payments due quarterly',
    indigenous_note = ''
WHERE title LIKE '%rates%darwin%';

UPDATE howto_guides SET
    fee = 'Free',
    processing_time = 'Enrolment confirmed within 1–5 business days; contact school directly',
    indigenous_note = 'For students with special learning needs or from remote communities, contact the School Support Officer before enrolment to arrange appropriate support.'
WHERE title LIKE '%school%';

UPDATE howto_guides SET
    fee = 'Free',
    processing_time = '4–8 weeks depending on case complexity',
    indigenous_note = 'Aboriginal and Torres Strait Islander clients may be eligible for specialist assistance through the North Australian Aboriginal Justice Agency (NAAJA) — call 1800 898 251.'
WHERE title LIKE '%legal aid%';

UPDATE howto_guides SET
    fee = 'Free',
    processing_time = 'Varies — waiting list can be months to years depending on demand and need category',
    indigenous_note = 'Remote housing applications are managed separately through NT Housing Remote offices. Contact your local Housing NT office or Community Housing organisation.'
WHERE title LIKE '%public housing%';
