declare namespace Express {
  export interface Request {
    id?: string;
    user?: {
      id: string;
      email: string;
      roles: string[];
    };
  }
}
