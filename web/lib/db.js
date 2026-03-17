import Database from 'better-sqlite3';
import path from 'path';

import { STATE_ABBREVS } from './constants.js';

// DB lives one level above the web/ directory
const DB_PATH = process.env.DB_PATH ?? path.join(process.cwd(), '..', 'healthcare.db');

const CAREER_SHORT = {
  'Occupational Therapists':   'OT',
  'Physical Therapists':       'PT',
  'Radiation Therapists':      'RT',
  'Speech-Language Pathologists': 'SLP',
};

/**
 * Returns every program row in the shape ProgramComparison expects.
 * Scaffold fields (cost, lengthMonths) are null until pipeline populates them.
 * areaSalary comes from the LEFT JOIN on employment_stats (BLS state mean).
 */
/**
 * Returns salary data for all states for one occupation.
 * Missing states have null wage fields. Abbreviation resolved from STATE_ABBREVS.
 */
export function getMapData(occupationName) {
  const db = new Database(DB_PATH, { readonly: true });
  const rows = db.prepare(`
    SELECT
      s.name               AS state_name,
      e.annual_mean_wage,
      e.annual_median_wage,
      e.number_of_employees
    FROM states s
    LEFT JOIN employment_stats e
        ON  e.state_id      = s.id
        AND e.occupation_id = (SELECT id FROM occupations WHERE name = ?)
    ORDER BY s.name
  `).all(occupationName);
  db.close();

  return rows.map(r => ({
    stateName:        r.state_name,
    stateAbbrev:      STATE_ABBREVS[r.state_name] ?? null,
    annualMeanWage:   r.annual_mean_wage   ?? null,
    annualMedianWage: r.annual_median_wage ?? null,
    employees:        r.number_of_employees ?? null,
  }));
}

/**
 * Returns national salary percentiles + employment + growth for one occupation.
 * Returns null if no data found.
 */
export function getNationalStats(occupationName) {
  const db = new Database(DB_PATH, { readonly: true });
  const row = db.prepare(`
    SELECT
      ns.employment,
      ns.annual_mean,
      ns.annual_10th   AS p10,
      ns.annual_25th   AS p25,
      ns.annual_median AS median,
      ns.annual_75th   AS p75,
      ns.annual_90th   AS p90,
      ns.bls_growth_pct
    FROM occupation_national_stats ns
    JOIN occupations o ON o.id = ns.occupation_id
    WHERE o.name = ?
  `).get(occupationName);
  db.close();

  if (!row) return null;
  return {
    employment:   row.employment,
    annualMean:   row.annual_mean,
    p10:          row.p10,
    p25:          row.p25,
    median:       row.median,
    p75:          row.p75,
    p90:          row.p90,
    blsGrowthPct: row.bls_growth_pct,
  };
}

/**
 * Returns work setting salary breakdown sorted by pct_of_total DESC.
 */
export function getWorkSettings(occupationName) {
  const db = new Database(DB_PATH, { readonly: true });
  const rows = db.prepare(`
    SELECT
      ws.setting_name       AS setting_name,
      ws.pct_of_total       AS pct_of_total,
      ws.annual_mean_wage   AS mean_wage,
      ws.annual_median_wage AS median_wage
    FROM work_setting_salaries ws
    JOIN occupations o ON o.id = ws.occupation_id
    WHERE o.name = ?
    ORDER BY ws.pct_of_total DESC
  `).all(occupationName);
  db.close();

  return rows.map(r => ({
    settingName: r.setting_name,
    pctOfTotal:  r.pct_of_total,
    meanWage:    r.mean_wage   ?? null,
    medianWage:  r.median_wage ?? null,
  }));
}

/**
 * Returns aggregate program stats for one occupation.
 * graduates_tested is null for OT, RT, SLP — so totalGraduates/avgSize will be null.
 */
export function getProgramStats(occupationName) {
  const db = new Database(DB_PATH, { readonly: true });
  const row = db.prepare(`
    SELECT
      COUNT(*)                       AS num_programs,
      SUM(p.graduates_tested)        AS total_graduates,
      ROUND(AVG(p.graduates_tested)) AS avg_size
    FROM programs p
    JOIN occupations o ON o.id = p.occupation_id
    WHERE o.name = ?
  `).get(occupationName);
  db.close();

  return {
    numPrograms:    row?.num_programs    ?? 0,
    totalGraduates: row?.total_graduates ?? null,
    avgSize:        row?.avg_size        ?? null,
  };
}

export function getPrograms() {
  const db = new Database(DB_PATH, { readonly: true });

  const rows = db.prepare(`
    SELECT
      p.id,
      sch.name                            AS school,
      s.name                              AS state,
      o.name                              AS occupation,
      p.degree_type,
      p.board_pass_rate_first_time_2yr    AS pass_rate_first,
      p.graduates_tested,
      p.program_length_months,
      p.tuition_per_year,
      p.tuition_instate,
      p.tuition_is_oos,
      p.total_program_cost,
      sc.ownership,
      e.annual_mean_wage                  AS area_salary
    FROM programs p
    JOIN schools     sch ON sch.id = p.school_id
    JOIN states      s   ON s.id   = sch.state_id
    JOIN occupations o   ON o.id   = p.occupation_id
    LEFT JOIN employment_stats e
        ON  e.state_id      = sch.state_id
        AND e.occupation_id = p.occupation_id
    LEFT JOIN school_scorecard sc ON sc.school_id = p.school_id
    ORDER BY sch.name
  `).all();

  db.close();

  return rows.map(r => ({
    id:            r.id,
    name:          r.school,
    state:         r.state,
    career:        CAREER_SHORT[r.occupation] ?? r.occupation,
    degreeType:    r.degree_type,
    // Real data — present for PT (both) and OT (pass rate only)
    boardPassRate: r.pass_rate_first   ?? null,
    programSize:   r.graduates_tested  ?? null,
    // Scaffold — columns exist in DB, will be non-null once pipeline fills them
    lengthMonths:  r.program_length_months ?? null,
    cost:          r.total_program_cost    ?? null,   // total program cost (preferred display metric)
    tuitionPerYear: r.tuition_per_year     ?? null,   // annual rate (shown as OOS context)
    tuitionInstate: r.tuition_instate      ?? null,   // in-state annual rate (public schools)
    tuitionIsOos:   r.tuition_is_oos === 1 ? true : r.tuition_is_oos === 0 ? false : null,
    schoolType:     r.ownership === 1 ? 'public' : r.ownership != null ? 'private' : null,
    // Real data — BLS annual mean wage for the program's state + occupation
    areaSalary:    r.area_salary ?? null,
  }));
}
