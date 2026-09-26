import ai.arboresce.Arboresce;

class Consumer {
    public static void main(String[] args) {
        for (int i = 0; i < 10000; i++) {
            if (!Arboresce.name().equals("Arboresce")) {
                throw new AssertionError("name");
            }
        }
        Arboresce.printName();
    }
}
