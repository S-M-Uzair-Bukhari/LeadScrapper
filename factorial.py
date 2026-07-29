def factorial(n):
    """
    Calculates the factorial of a non-negative integer n (n!).

    Args:
        n (int): The number for which to calculate the factorial. Must be non-negative.

    Returns:
        int: The factorial of n. Returns 1 if n is 0, and None if n is negative.
    """
    if n < 0:
        print("Error: Factorial is not defined for negative numbers.")
        return None
    elif n == 0:
        return 1
    else:
        result = 1
        for i in range(1, n + 1):
            result *= i
        return result

if __name__ == "__main__":
    try:
        # Get input from the user
        num_str = input("Enter a non-negative integer to calculate its factorial: ")
        num = int(num_str)

        # Calculate and print the result
        fact = factorial(num)
        if fact is not None:
            print(f"The factorial of {num} ({num}!) is: {fact}")

    except ValueError:
        print("Invalid input. Please enter a valid integer.")