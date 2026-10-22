export type Role = 'officer' | 'fraud' | 'manager' | 'customer';

/** The signed-in account, as GET /auth/me returns it (never the password hash). */
export interface User {
  username: string;
  role: Role;
  full_name: string;
  approval_limit_myr: number | null;
}

export const ROLE_LABEL: Record<Role, string> = {
  officer: 'Complaints officer',
  fraud: 'Fraud analyst',
  manager: 'Manager',
  customer: 'Customer',
};

export const isStaff = (user: User | null): boolean => !!user && user.role !== 'customer';
