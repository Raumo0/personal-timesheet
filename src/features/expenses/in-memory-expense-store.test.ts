import { expenseStoreContract, expenseStoreContractDefaults } from "./expense-store.contract";
import { InMemoryExpenseStore } from "./in-memory-expense-store";

expenseStoreContract(
  "InMemoryExpenseStore",
  (seed) => new InMemoryExpenseStore({ ...seed, ...expenseStoreContractDefaults }),
);
