/**
 * Zod schemas for client-side form validation.
 * Flask API endpoints enforce equivalent rules server-side (see api_validation.py).
 */

import { z } from "zod";
import { sanitizeTextInput } from "./sanitize";

const noControlChars = (value: string) => !/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(value);

export const emailSchema = z
  .string()
  .trim()
  .min(1, "Enter your email address.")
  .email("Enter a valid email address.")
  .max(254);

export const passwordSchema = z
  .string()
  .min(6, "Password must be at least 6 characters.")
  .max(128, "Password is too long.");

export const signInFormSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Enter your password.").max(128),
});

export const signUpFormSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
  ageConfirmed: z.literal(true, {
    message: "You must confirm that you are at least 18 years of age.",
  }),
});

export const pdfReferenceSchema = z
  .string()
  .transform((value) => sanitizeTextInput(value, 200))
  .pipe(
    z
      .string()
      .min(2, "Please enter an organisation name or reference URL.")
      .max(200, "Reference is too long (max 200 characters).")
      .refine(noControlChars, "Reference contains invalid characters."),
  );

export const scanUrlPayloadSchema = z.object({
  url: z.string().trim().min(1, "Please enter a website URL.").max(2048),
  privacy_url: z.string().max(2048).optional(),
  terms_url: z.string().max(2048).optional(),
  cookie_url: z.string().max(2048).optional(),
});

export type SignInFormInput = z.infer<typeof signInFormSchema>;
export type SignUpFormInput = z.infer<typeof signUpFormSchema>;

/** Format Zod errors for inline form display. */
export function firstZodError(error: z.ZodError): string {
  return error.issues[0]?.message ?? "Invalid input.";
}
